"""
Social Platform and Post URL Classifier.
Evaluates domains and URL paths against declarative rules in platforms.yaml.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
import logging
import re
import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "platforms.yaml"


class PlatformClassifier:
    """Classifies candidate URLs into social platforms and post-like content."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.domain_to_platform: Dict[str, str] = {}
        self.platform_patterns: Dict[str, List[re.Pattern]] = {}
        self._load_config()

    def _load_config(self):
        if not self.config_path.exists():
            logger.warning(f"platforms.yaml not found at {self.config_path}, using built-in defaults.")
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            platforms = data.get("platforms", {})
            for plat_key, cfg in platforms.items():
                name = cfg.get("name", plat_key)
                domains = cfg.get("domains", [])
                patterns = cfg.get("post_path_patterns", [])

                for dom in domains:
                    self.domain_to_platform[dom.lower()] = name

                compiled = [re.compile(p) for p in patterns]
                if name in self.platform_patterns:
                    self.platform_patterns[name].extend(compiled)
                else:
                    self.platform_patterns[name] = compiled

            logger.info(f"Loaded {len(self.domain_to_platform)} social domain mappings and {len(self.platform_patterns)} pattern sets.")
        except Exception as e:
            logger.error(f"Failed to parse platforms.yaml: {e}")

    def classify(self, url: str) -> Tuple[Optional[str], bool, bool]:
        """
        Classifies a URL.

        :param url: Full webpage URL
        :return: (platform_name, is_social_domain, is_post_url)
        """
        if not url or not url.lower().startswith(("http://", "https://")):
            return None, False, False

        try:
            parsed = urlparse(url)
            netloc = parsed.netloc.lower()
            if ":" in netloc:
                netloc = netloc.split(":")[0]

            # Match domain (supporting subdomains like m.facebook.com, old.reddit.com)
            platform_name = None
            if netloc in self.domain_to_platform:
                platform_name = self.domain_to_platform[netloc]
            else:
                for dom, p_name in self.domain_to_platform.items():
                    if netloc.endswith("." + dom):
                        platform_name = p_name
                        break

            if not platform_name:
                return None, False, False

            is_social_domain = True
            is_post_url = False

            # Check for non-post paths (homepages, login, search, settings, etc.)
            clean_path = parsed.path.rstrip("/")
            if not clean_path or clean_path == "":
                # Generic homepage -> Not a post URL
                return platform_name, is_social_domain, False

            lower_path = parsed.path.lower()
            non_post_prefixes = (
                "/login", "/signin", "/signup", "/search", "/explore",
                "/accounts", "/about", "/help", "/terms", "/privacy",
                "/settings", "/logout", "/auth"
            )
            if any(lower_path.startswith(prefix) for prefix in non_post_prefixes):
                return platform_name, is_social_domain, False

            # Check post patterns configured for this platform
            patterns = self.platform_patterns.get(platform_name, [])
            for pat in patterns:
                if pat.search(parsed.path):
                    is_post_url = True
                    break

            return platform_name, is_social_domain, is_post_url

        except Exception as e:
            logger.warning(f"Error classifying URL '{url}': {e}")
            return None, False, False
