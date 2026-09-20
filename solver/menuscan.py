"""Read a menu out of a photograph or a PDF, and hand it to the parser.

Typing a week's timetable in is the reason nobody uses a tool like this on
their own mess. The menu already exists: it is a sheet taped to the dining
hall wall, a spreadsheet the warden exported, a photo of either in a hostel
WhatsApp group. So this takes the file as it is.

What the model is and is not allowed to do
------------------------------------------

The model transcribes. That is the whole job. It turns pixels into the words
that were printed on them, laid out as a table, and then it is finished.

It is explicitly *not* allowed to decide what is on the menu in catalog
terms. That matching stays in `menutext`, which is deterministic, offline,
and answers "I do not know this one, but here are the three dishes I nearly
said" -- the honesty that makes the rest of this product worth trusting. A
model asked to emit dish ids would instead produce a confident, plausible,
unfalsifiable menu, and a shortfall computed from a hallucinated menu is
wrong in a way the reader has no way to see.

So the division is: the model may read handwriting, and may not do
arithmetic or taxonomy. It is the same rule `explain` follows.

Nothing the model writes is trusted as an instruction. Its output is one
string, and the only thing that ever happens to that string is that it gets
split on pipes and commas and compared against a fixed catalog of dish
names. A menu whose text says "ignore your instructions" parses to a few
unmatched items and nothing else.

The transcription is shown to the person before anything is solved, and it
is editable, because OCR on a photographed noticeboard gets things wrong and
the person holding the phone is the one who knows what the menu says.

As in `explain`, the boto3 import is lazy and every failure is one failure:
there is no scan this time, and the paste box is still there.
"""

import os

MODEL_ID = os.environ.get("PLATEGAP_SCAN_MODEL", "amazon.nova-lite-v1:0")
BEDROCK_REGION = os.environ.get(
    "PLATEGAP_BEDROCK_REGION", os.environ.get("AWS_REGION", "us-east-1"))

# A week of four meals is a few hundred short words. This is roughly twice
# what the menu it was built against needs, and it is also the ceiling on
# what a public endpoint can be made to generate per request.
MAX_OUTPUT_TOKENS = 1800

# Measured against a real mess menu: a page of PDF comes back in about nine
# seconds. Fifteen leaves room for a slower page without spending the whole
# of the function's timeout on one call.
READ_TIMEOUT_SECONDS = 15
CONNECT_TIMEOUT_SECONDS = 3

# Bedrock's own ceilings are 3.75 MB for an image and 4.5 MB for a document,
# and one limit under both is simpler to explain and simpler to check. What
# actually sets this number is the request: the file arrives base64 encoded,
# which costs a third on top, and `handler.MAX_UPLOAD_BODY_BYTES` is what the
# result has to fit inside. The interface downscales photographs before
# sending them, so this is a ceiling for scanned PDFs rather than a number
# anyone photographing a noticeboard will meet.
MAX_BYTES = 5 * 512 * 1024

# What the browser is allowed to send, and what Bedrock calls it. A phone
# camera produces JPEG, a scanner produces PDF, a screenshot produces PNG,
# and that is the whole of the real world here.
FORMATS = {
    "pdf": ("document", "pdf"),
    "png": ("image", "png"),
    "jpeg": ("image", "jpeg"),
    "jpg": ("image", "jpeg"),
    "webp": ("image", "webp"),
    "gif": ("image", "gif"),
}

# Deliberately an instruction to copy, not to understand.
#
# Two things were tried here and made it worse, both for the same reason.
# Asking for the days down the side instead of across the top means asking a
# small model to transpose a grid, and it responds by dropping most of the
# cells and then repeating one row until it runs out of tokens. Adding a
# sentence about the row of items served every day had the same effect: it
# emitted the row label and none of the contents. Every instruction beyond
# "write down what is printed" competes with the transcription for the
# model's attention, and the transcription loses.
#
# So the prompt asks for a faithful copy in the layout the page already has,
# which is also the layout `menutext` reads directly -- days across the top
# is how a mess noticeboard is drawn.
PROMPT = (
    "This is a weekly canteen or mess menu. Write it out as a markdown "
    "table, one row per meal, one column per day of the week. Copy the dish "
    "names exactly as they are written, including any spelling mistakes. Do "
    "not translate, rename, expand, abbreviate or invent anything. If a cell "
    "is blank, leave it blank. Output the table and nothing else."
)

_CLIENT = None


class ScanUnavailable(RuntimeError):
    """The file could not be read, and the person should type instead."""


def content_block(data, kind):
    """The Converse content block for one uploaded file.

    Raises `ScanUnavailable` for anything we will not send, so that the size
    and type checks live next to the numbers they are checking.
    """
    if kind not in FORMATS:
        raise ScanUnavailable(
            "%s is not a kind of file this can read; send a PDF or a photo"
            % kind)
    if not data:
        raise ScanUnavailable("that file is empty")
    if len(data) > MAX_BYTES:
        raise ScanUnavailable(
            "that file is %.1f MB and the limit is %d MB"
            % (len(data) / 1048576.0, MAX_BYTES // 1048576))

    block, fmt = FORMATS[kind]
    if block == "document":
        # Bedrock validates document names and rejects punctuation, so this
        # is a constant rather than anything the caller chose.
        return {"document": {"format": fmt, "name": "menu",
                             "source": {"bytes": data}}}
    return {"image": {"format": fmt, "source": {"bytes": data}}}


def call_model(block, model_id=None):
    """Invoke Bedrock, importing boto3 only if we get this far."""
    global _CLIENT
    model_id = model_id or MODEL_ID
    if not model_id or model_id.lower() in ("off", "none", "disabled"):
        raise ScanUnavailable("reading uploaded menus is switched off here")

    if _CLIENT is None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as problem:
            raise ScanUnavailable("no AWS SDK in this runtime: %s" % problem)
        try:
            _CLIENT = boto3.client(
                "bedrock-runtime", region_name=BEDROCK_REGION,
                config=Config(connect_timeout=CONNECT_TIMEOUT_SECONDS,
                              read_timeout=READ_TIMEOUT_SECONDS,
                              retries={"max_attempts": 1}))
        except Exception as problem:
            raise ScanUnavailable("no Bedrock client: %s" % problem)

    try:
        response = _CLIENT.converse(
            modelId=model_id,
            messages=[{"role": "user",
                       "content": [block, {"text": PROMPT}]}],
            # Zero temperature because this is transcription. There is a
            # right answer printed on the page and no reason to sample away
            # from it.
            inferenceConfig={"maxTokens": MAX_OUTPUT_TOKENS,
                             "temperature": 0.0})
    except Exception as problem:
        raise ScanUnavailable("%s: %s" % (type(problem).__name__, problem))

    try:
        parts = response["output"]["message"]["content"]
        text = "".join(part.get("text", "") for part in parts)
    except (KeyError, TypeError, AttributeError) as problem:
        raise ScanUnavailable("the model answered in a shape we do not "
                              "understand: %s" % problem)

    return text, response.get("stopReason"), response.get("usage") or {}


def read(data, kind, invoke=None, model_id=None):
    """Transcribe one uploaded menu.

    `invoke` is the seam the tests use: anything callable that takes a
    content block and returns `(text, stopReason, usage)`.
    """
    block = content_block(data, kind)
    try:
        text, stop_reason, usage = (invoke or call_model)(block)
    except ScanUnavailable:
        raise
    except Exception as problem:
        # `call_model` already turns everything it can see into a
        # `ScanUnavailable`. This is the same promise made at the edge of the
        # module rather than inside one implementation of it, so that no
        # future way of reaching Bedrock can turn a busy model into a 500.
        raise ScanUnavailable("%s: %s" % (type(problem).__name__, problem))

    if not text or not text.strip():
        raise ScanUnavailable("nothing readable came back from that file")

    warnings = []
    if stop_reason == "max_tokens":
        # The table is cut off rather than wrong, and half a week is still
        # worth showing -- but only if we say so, because the missing days
        # would otherwise look like days the mess serves nothing.
        warnings.append("this menu was longer than one read allows, so the "
                        "transcription stops partway; check the last days "
                        "and add anything missing")

    return {
        "text": text.strip(),
        "warnings": warnings,
        "tokens": {"in": usage.get("inputTokens"),
                   "out": usage.get("outputTokens")},
    }
