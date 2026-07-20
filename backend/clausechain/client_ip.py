import ipaddress

from django.conf import settings


def get_client_ip(request):
    remote_addr = (request.META.get("REMOTE_ADDR") or "").strip()
    forwarded_for = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    trusted_proxy_ips = set(getattr(settings, "TRUSTED_PROXY_IPS", []))

    if remote_addr and remote_addr in trusted_proxy_ips and forwarded_for:
        forwarded_chain = [
            part.strip() for part in forwarded_for.split(",") if part and part.strip()
        ]
        if forwarded_chain:
            return forwarded_chain[0]

    return remote_addr


def ip_matches_allowlist(ip_address, allowlist):
    normalized_ip = (ip_address or "").strip()
    if not normalized_ip:
        return False

    try:
        parsed_ip = ipaddress.ip_address(normalized_ip)
    except ValueError:
        return False

    for candidate in allowlist or []:
        normalized_candidate = (candidate or "").strip()
        if not normalized_candidate:
            continue

        try:
            if "/" in normalized_candidate:
                network = ipaddress.ip_network(normalized_candidate, strict=False)
                if parsed_ip in network:
                    return True
            elif parsed_ip == ipaddress.ip_address(normalized_candidate):
                return True
        except ValueError:
            continue

    return False
