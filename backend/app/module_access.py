from __future__ import annotations

# Product modules a user can be granted, independent of the per-country
# access_profile: "radar" is the live multi-country radar (Peru/Chile/
# Argentina pages), "historico_peru" / "historico_chile" the open-data history
# modules (CONOSCE / ChileCompra).
VALID_MODULES: tuple[str, ...] = ("radar", "historico_peru", "historico_chile")
DEFAULT_MODULES = "radar"


def parse_module_access(value: str | None) -> set[str]:
    if not value:
        return set()
    return {module for module in value.split(",") if module in VALID_MODULES}


def format_module_access(modules: set[str] | list[str] | tuple[str, ...]) -> str:
    selected = set(modules)
    return ",".join(module for module in VALID_MODULES if module in selected)


def has_module_access(module_access: str | None, module: str) -> bool:
    return module in parse_module_access(module_access)
