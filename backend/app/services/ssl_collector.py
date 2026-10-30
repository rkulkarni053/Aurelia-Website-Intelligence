import socket
import ssl
import time
from datetime import datetime, timezone

import httpx
from cryptography import x509
from cryptography.x509.oid import NameOID


_OID_NAMES = {
    NameOID.COMMON_NAME: "commonName",
    NameOID.ORGANIZATION_NAME: "organizationName",
    NameOID.COUNTRY_NAME: "countryName",
    NameOID.ORGANIZATIONAL_UNIT_NAME: "organizationalUnitName",
    NameOID.LOCALITY_NAME: "localityName",
    NameOID.STATE_OR_PROVINCE_NAME: "stateOrProvinceName",
}


def _x509_name_to_dict(name: x509.Name) -> dict:
    result = {}
    for attr in name:
        key = _OID_NAMES.get(attr.oid, attr.oid.dotted_string)
        result[key] = attr.value
    return result


def _name_to_dict(name) -> dict:
    """Convert getpeercert's nested tuples into a flat dict."""
    result = {}
    for rdn in name or ():
        for key, value in rdn:
            result[key] = value
    return result


def _check_http_redirect(domain: str) -> dict:
    try:
        response = httpx.get(
            f"http://{domain}/",
            follow_redirects=False,
            timeout=10.0,
            headers={"User-Agent": "WebsiteIntelligenceBot/0.1"},
        )
        location = response.headers.get("location", "")
        return {
            "status_code": response.status_code,
            "location": location or None,
            "redirects_to_https": (
                response.status_code in (301, 302, 303, 307, 308)
                and location.lower().startswith("https://")
            ),
            "error": None,
        }
    except Exception as exc:
        return {
            "status_code": None,
            "location": None,
            "redirects_to_https": False,
            "error": str(exc),
        }


def _read_unverified(domain: str, port: int) -> dict:
    """Connect WITHOUT verification, only to read certificate details.

    The result is evidence about a certificate that failed validation.
    It must never be treated as trusted.
    """
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    with socket.create_connection((domain, port), timeout=10) as sock:
        with context.wrap_socket(sock, server_hostname=domain) as tls:
            der = tls.getpeercert(binary_form=True)
            cipher = tls.cipher()
            tls_version = tls.version()

    cert = x509.load_der_x509_certificate(der)

    try:
        san_ext = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        )
        sans = san_ext.value.get_values_for_type(x509.DNSName)
    except x509.ExtensionNotFound:
        sans = []

    not_before = cert.not_valid_before_utc
    not_after = cert.not_valid_after_utc

    return {
        "tls_version": tls_version,
        "cipher": (
            {"name": cipher[0], "protocol": cipher[1], "bits": cipher[2]}
            if cipher
            else None
        ),
        "issuer": _x509_name_to_dict(cert.issuer),
        "subject": _x509_name_to_dict(cert.subject),
        "serial_number": format(cert.serial_number, "X"),
        "valid_from": not_before.isoformat(),
        "valid_until": not_after.isoformat(),
        "days_remaining": int((not_after.timestamp() - time.time()) // 86400),
        "subject_alt_names": list(sans),
    }


def collect_ssl(domain: str, port: int = 443) -> dict:
    """Collect TLS certificate evidence. Never raises; errors are recorded."""
    evidence = {
        "domain": domain,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "https_enabled": False,
        "certificate_valid": False,
        "details_source": None,
        "tls_version": None,
        "cipher": None,
        "issuer": None,
        "subject": None,
        "serial_number": None,
        "valid_from": None,
        "valid_until": None,
        "days_remaining": None,
        "subject_alt_names": [],
        "error": None,
        "http_to_https": None,
    }

    context = ssl.create_default_context()

    try:
        with socket.create_connection((domain, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as tls:
                cert = tls.getpeercert()
                cipher = tls.cipher()

                evidence["https_enabled"] = True
                evidence["certificate_valid"] = True
                evidence["details_source"] = "verified"
                evidence["tls_version"] = tls.version()

                if cipher:
                    evidence["cipher"] = {
                        "name": cipher[0],
                        "protocol": cipher[1],
                        "bits": cipher[2],
                    }

                evidence["issuer"] = _name_to_dict(cert.get("issuer"))
                evidence["subject"] = _name_to_dict(cert.get("subject"))
                evidence["serial_number"] = cert.get("serialNumber")
                evidence["subject_alt_names"] = [
                    value for _, value in cert.get("subjectAltName", ())
                ]

                not_before = ssl.cert_time_to_seconds(cert["notBefore"])
                not_after = ssl.cert_time_to_seconds(cert["notAfter"])

                evidence["valid_from"] = datetime.fromtimestamp(
                    not_before, timezone.utc
                ).isoformat()
                evidence["valid_until"] = datetime.fromtimestamp(
                    not_after, timezone.utc
                ).isoformat()
                evidence["days_remaining"] = int(
                    (not_after - time.time()) // 86400
                )

    except ssl.SSLCertVerificationError as exc:
        # The server speaks TLS, but the certificate failed validation.
        evidence["https_enabled"] = True
        evidence["certificate_valid"] = False
        evidence["error"] = (
            f"Certificate verification failed: {exc.verify_message}"
        )

        try:
            evidence.update(_read_unverified(domain, port))
            evidence["details_source"] = "unverified"
        except Exception as fallback_exc:
            evidence["details_source"] = "unavailable"
            evidence["error"] += (
                f" (could not read certificate details: "
                f"{type(fallback_exc).__name__}: {fallback_exc})"
            )

    except Exception as exc:
        evidence["error"] = f"{type(exc).__name__}: {exc}"

    evidence["http_to_https"] = _check_http_redirect(domain)

    return evidence
