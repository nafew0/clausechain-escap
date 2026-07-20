import base64
import json
from urllib.parse import urlparse
from urllib.request import urlopen

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding


class BkashSNSVerificationError(Exception):
    pass


class BkashSNSPayloadError(Exception):
    pass


def parse_sns_message(raw_body):
    try:
        payload = json.loads((raw_body or b"").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BkashSNSPayloadError("Webhook payload is not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise BkashSNSPayloadError("Webhook payload is not valid JSON.")

    return payload


def _validate_signing_cert_url(signing_cert_url):
    parsed = urlparse((signing_cert_url or "").strip())
    if parsed.scheme != "https":
        raise BkashSNSVerificationError("SNS signing certificate must use HTTPS.")
    if not parsed.netloc.endswith(".amazonaws.com"):
        raise BkashSNSVerificationError("SNS signing certificate host is not trusted.")
    if not parsed.path.endswith(".pem"):
        raise BkashSNSVerificationError("SNS signing certificate URL is invalid.")
    return signing_cert_url


def _build_string_to_sign(message):
    message_type = (message.get("Type") or "").strip()
    if message_type == "Notification":
        ordered_fields = [
            "Message",
            "MessageId",
            "Subject",
            "Timestamp",
            "TopicArn",
            "Type",
        ]
    elif message_type in {"SubscriptionConfirmation", "UnsubscribeConfirmation"}:
        ordered_fields = [
            "Message",
            "MessageId",
            "SubscribeURL",
            "Timestamp",
            "Token",
            "TopicArn",
            "Type",
        ]
    else:
        raise BkashSNSVerificationError("SNS message type is not supported.")

    parts = []
    for field_name in ordered_fields:
        field_value = message.get(field_name)
        if field_value in (None, ""):
            continue
        parts.append(f"{field_name}\n{field_value}")
    return "\n".join(parts)


def verify_sns_message_signature(message, *, expected_topic_arn=""):
    topic_arn = (message.get("TopicArn") or "").strip()
    if expected_topic_arn and topic_arn != expected_topic_arn:
        raise BkashSNSVerificationError("SNS topic ARN did not match the expected topic.")

    signing_cert_url = _validate_signing_cert_url(message.get("SigningCertURL"))
    signature = message.get("Signature")
    signature_version = str(message.get("SignatureVersion") or "").strip()
    if not signature or signature_version not in {"1", "2"}:
        raise BkashSNSVerificationError("SNS signature metadata is incomplete.")

    with urlopen(signing_cert_url, timeout=10) as response:
        certificate_data = response.read()

    certificate = x509.load_pem_x509_certificate(certificate_data)
    public_key = certificate.public_key()
    hash_algorithm = hashes.SHA1() if signature_version == "1" else hashes.SHA256()
    string_to_sign = _build_string_to_sign(message).encode("utf-8")

    try:
        public_key.verify(
            base64.b64decode(signature),
            string_to_sign,
            padding.PKCS1v15(),
            hash_algorithm,
        )
    except Exception as exc:
        raise BkashSNSVerificationError("SNS signature verification failed.") from exc


def confirm_sns_subscription(message):
    subscribe_url = (message.get("SubscribeURL") or "").strip()
    if not subscribe_url:
        raise BkashSNSPayloadError("SNS subscription confirmation did not include SubscribeURL.")

    parsed = urlparse(subscribe_url)
    if parsed.scheme != "https" or not parsed.netloc.endswith(".amazonaws.com"):
        raise BkashSNSVerificationError("SNS subscription confirmation URL is not trusted.")

    with urlopen(subscribe_url, timeout=10) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_notification_payload(message):
    raw_message = message.get("Message")
    if isinstance(raw_message, dict):
        payload = raw_message
    else:
        try:
            payload = json.loads(raw_message or "{}")
        except json.JSONDecodeError as exc:
            raise BkashSNSPayloadError("SNS notification message is not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise BkashSNSPayloadError("SNS notification message is not valid JSON.")

    return payload
