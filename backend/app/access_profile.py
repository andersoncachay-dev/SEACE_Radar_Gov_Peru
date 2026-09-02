from __future__ import annotations

VALID_COUNTRIES: tuple[str, ...] = ("peru", "chile", "argentina")


def parse_access_profile(value: str) -> set[str]:
    """A user's access_profile is a comma-separated subset of VALID_COUNTRIES
    (e.g. "peru,chile"). "both" is the legacy all-countries value predating
    Argentina support and is still accepted for backward compatibility."""
    if not value:
        return set()
    if value == "both":
        return set(VALID_COUNTRIES)
    return {country for country in value.split(",") if country in VALID_COUNTRIES}


def format_access_profile(countries: set[str] | list[str] | tuple[str, ...]) -> str:
    selected = set(countries)
    return ",".join(country for country in VALID_COUNTRIES if country in selected)


def has_country_access(access_profile: str, country: str) -> bool:
    return country in parse_access_profile(access_profile)
