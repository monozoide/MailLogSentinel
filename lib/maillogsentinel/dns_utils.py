"""DNS lookup utilities with caching for MailLogSentinel."""

import socket
import functools
import time
import logging
from typing import Optional, Tuple, Callable, Dict, Any

from . import config

# --- Global DNS Cache Variables ---
# These store the active cache function and its settings after initialization.
CACHED_DNS_LOOKUP_FUNC: Optional[
    Callable[[str], Tuple[Optional[str], Optional[str], float]]
] = None
DNS_CACHE_SETTINGS: Dict[str, Any] = (
    {}
)  # Stores effective settings like 'enabled', 'ttl', 'max_size'


def _perform_actual_reverse_lookup(ip: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Performs the actual reverse DNS lookup for an IP address.

    This function directly queries the DNS system to resolve an IP address
    to a hostname. It does not use any caching.

    Args:
        ip: The IP address (string) to look up.

    Returns:
        A tuple containing:
            - The hostname (str) if the lookup is successful.
            - An error string (str) if the lookup fails (e.g., "Errno 1", "Timeout").
        If successful, the error string is None. If failed, the hostname is None.
    """
    try:
        hostname = socket.gethostbyaddr(ip)[0]
        return hostname, None
    except (socket.herror, socket.gaierror, socket.timeout) as e:
        error_code = getattr(e, "errno", None)
        error_str: Optional[str] = None

        if error_code is not None:
            error_str = f"ERRNO {error_code}"
        elif isinstance(e, socket.timeout):
            error_str = "Timeout"
        else:
            error_str = "Failed (Unknown)"
        return None, error_str


def initialize_dns_cache(
    app_config: "config.AppConfig", logger: Optional[logging.Logger] = None
):
    """
    Initializes the DNS caching mechanism based on AppConfig settings.

    This function configures the DNS lookup caching behavior for the application.
    If caching is enabled in `app_config`, it sets up an LRU (Least Recently Used)
    cache for DNS lookups. The cache settings (size, TTL) are taken from
    `app_config`.

    The global `CACHED_DNS_LOOKUP_FUNC` is updated to point to the cached
    lookup function, or set to `None` if caching is disabled. The effective
    cache settings are stored in the global `DNS_CACHE_SETTINGS` dictionary.

    Args:
        app_config: An `AppConfig` instance containing DNS cache configuration
                    (e.g., `dns_cache_enabled`, `dns_cache_size`,
                    `dns_cache_ttl_seconds`).
        logger: An optional `logging.Logger` instance for logging messages.
                If None, a default logger for this module is used.
    """
    global CACHED_DNS_LOOKUP_FUNC

    # Store the settings that will be used by reverse_lookup
    DNS_CACHE_SETTINGS["enabled"] = app_config.dns_cache_enabled
    DNS_CACHE_SETTINGS["ttl"] = app_config.dns_cache_ttl_seconds
    DNS_CACHE_SETTINGS["max_size"] = (
        app_config.dns_cache_size
    )  # Stored for reference, not directly used by lru_cache after init

    effective_logger = logger if logger else logging.getLogger(__name__)

    if app_config.dns_cache_enabled:
        # The lru_cache decorator uses the function's code object, so maxsize
        # must be fixed at definition. If max_size needs to be dynamic after
        # startup, lru_cache would need to be re-applied, which typically means
        # redefining the cached function or managing multiple cache instances.
        # For this application, initializing once at startup is standard.
        @functools.lru_cache(maxsize=app_config.dns_cache_size)
        def _dynamically_cached_lookup(
            ip: str,
        ) -> Tuple[Optional[str], Optional[str], float]:
            # This function will be the one decorated by lru_cache
            hostname, error_str = _perform_actual_reverse_lookup(ip)
            return hostname, error_str, time.time()  # Store timestamp with the result

        CACHED_DNS_LOOKUP_FUNC = _dynamically_cached_lookup
        effective_logger.info(
            f"DNS cache initialized with max_size: {app_config.dns_cache_size}, "
            f"TTL: {app_config.dns_cache_ttl_seconds}s"
        )
    else:
        CACHED_DNS_LOOKUP_FUNC = None  # Ensure it's None if caching is disabled
        effective_logger.info("DNS cache is disabled by configuration.")


def reverse_lookup(
    ip: str, logger: logging.Logger
) -> Tuple[Optional[str], Optional[str]]:
    """
    Performs a reverse DNS lookup for the given IP address.

    This function attempts to find the hostname associated with an IP address.
    If DNS caching is enabled (via `initialize_dns_cache` and `AppConfig`),
    it first checks the cache. Cache entries are considered stale if their
    Time-To-Live (TTL) has expired, triggering a fresh lookup.

    If caching is disabled or the item is not in the cache (or stale),
    it performs a direct DNS lookup.

    Args:
        ip: The IP address (string) to look up.
        logger: A `logging.Logger` instance for logging debug messages
                related to cache usage or lookup failures.

    Returns:
        A tuple containing:
            - The hostname (str) if the lookup is successful (either from cache
              or fresh).
            - An error string (str) if the lookup fails (e.g., "Errno 1", "Timeout").
        If successful, the error string is None. If failed, the hostname is None.
    """

    cache_is_effectively_enabled = DNS_CACHE_SETTINGS.get("enabled", False)

    if not cache_is_effectively_enabled or CACHED_DNS_LOOKUP_FUNC is None:
        if logger:
            logger.debug(f"DNS cache not used for {ip}. Performing direct lookup.")
        hostname, error_str = _perform_actual_reverse_lookup(ip)
        if error_str and logger:
            logger.debug(f"Reverse lookup failed for IP {ip}: {error_str}")
        return hostname, error_str

    dns_ttl_seconds = DNS_CACHE_SETTINGS.get("ttl", 3600)
    cached_hostname, cached_error_str, timestamp = CACHED_DNS_LOOKUP_FUNC(ip)
    final_hostname: Optional[str] = None
    final_error_str: Optional[str] = None

    if time.time() - timestamp > dns_ttl_seconds:
        if logger:
            logger.info(f"DNS cache for {ip} is stale. Performing fresh lookup.")
        fresh_hostname, fresh_error_str = _perform_actual_reverse_lookup(ip)
        final_hostname = fresh_hostname
        final_error_str = fresh_error_str
    else:
        if logger:
            logger.debug(f"Using valid cached DNS entry for {ip}.")
        final_hostname = cached_hostname
        final_error_str = cached_error_str

    if final_error_str and logger:
        logger.debug(f"Reverse lookup for IP {ip} (cached/fresh): {final_error_str}")
    return final_hostname, final_error_str
