from .keywords import CORE_KEYWORDS, TARGET_ENTITIES, TARGET_REGIONS, ENTERPRISE_REQUIREMENTS
from .keyword_matching import contains_any_complete_phrase


def contains_any(text, terms):
    return contains_any_complete_phrase(text, terms)


def detectar_sector(row):
    texto = f"{row.get('entidad','')} {row.get('descripcion','')} {row.get('objeto','')}".lower()
    if any(x in texto for x in ["ugel", "educativa", "colegio", "institucion educativa"]): return "Educacion"
    if any(x in texto for x in ["diresa", "red de salud", "salud", "hospital"]): return "Salud"
    if "gobierno regional" in texto or "gore" in texto: return "Gobierno Regional"
    if any(x in texto for x in ["marina", "ejercito", "ejército", "fuerza aerea", "fuerza aérea", "provias", "mtc"]): return "Infraestructura/Defensa"
    if "bcrp" in texto or "banco central" in texto: return "Banca Publica"
    if "san gaban" in texto or "electrica" in texto or "energ" in texto: return "Energia"
    return "Otros"


def _default_config():
    return {
        "priority_a_min": 70, "priority_b_min": 45, "attractive_amount_min": 100000,
        "factors": {
            "keyword": {"points": 25, "enabled": True, "value": ",".join(CORE_KEYWORDS)},
            "target_entity": {"points": 20, "enabled": True, "value": ",".join([*TARGET_ENTITIES, "provias", "mtc"])},
            "priority_region": {"points": 15, "enabled": True, "value": ",".join(TARGET_REGIONS)},
            "attractive_amount": {"points": 15, "enabled": True, "value": "100000"},
            "quick_purchase": {"points": 10, "enabled": True, "value": "menor_8"},
            "queries_and_proposal": {"points": 30, "enabled": True, "value": "consultas y propuesta,consulta y cotiz"},
            "proposal_only": {"points": 20, "enabled": True, "value": "vigente para propuesta,solo para propuesta,sólo para propuesta,solo para cotiz,sólo para cotiz"},
            "evaluation": {"points": 5, "enabled": True, "value": "en evalu"},
            "closed": {"points": -35, "enabled": True, "value": "cerrado"},
            "enterprise": {"points": 10, "enabled": True, "value": ",".join(ENTERPRISE_REQUIREMENTS)},
        },
    }


def calcular_score(row, config=None):
    config = config or _default_config()
    factors = config["factors"]
    descripcion = f"{row.get('descripcion','')} {row.get('objeto','')} {row.get('nomenclatura','')} {row.get('area_usuaria','')}".lower()
    entidad = str(row.get("entidad", "")).lower()
    region = str(row.get("region", "")).lower()
    estado = str(row.get("estado_comercial", "")).lower()
    origen = str(row.get("origen", "")).lower()
    score = 0
    motivos = []

    def terms(key):
        value = factors[key].get("value", "")
        return [term.strip().lower() for term in value.split(",") if term.strip()]

    def add(key, condition, reason):
        nonlocal score
        if condition and factors[key]["enabled"]:
            score += int(factors[key]["points"])
            motivos.append(reason)

    add("keyword", contains_any(descripcion, terms("keyword") or CORE_KEYWORDS), "Keyword conectividad/satelital")
    add("target_entity", contains_any(entidad, terms("target_entity") or TARGET_ENTITIES), "Entidad objetivo")
    add("priority_region", any(r == region or r in region for r in (terms("priority_region") or TARGET_REGIONS)), "Region priorizada")
    try:
        amount_min = float(factors["attractive_amount"].get("value", config["attractive_amount_min"]))
        add("attractive_amount", float(row.get("monto", 0) or 0) >= amount_min, "Monto atractivo")
    except Exception:
        pass
    add("quick_purchase", factors["quick_purchase"].get("value", "menor_8").lower() in origen, "Compra rápida menor a 8 UIT")
    if any(value in estado for value in terms("queries_and_proposal")):
        add("queries_and_proposal", True, "Vigente para consultas/cotización")
    elif any(value in estado for value in terms("proposal_only")):
        add("proposal_only", True, "Vigente solo para propuesta/cotización")
    elif any(value in estado for value in terms("evaluation")):
        add("evaluation", True, "En evaluación")
    elif any(value in estado for value in terms("closed")):
        add("closed", True, "Proceso cerrado")
        score = max(0, score)
    elif "revisar" in estado:
        motivos.append("Revisar cronograma")
    add("enterprise", contains_any(descripcion, terms("enterprise") or ENTERPRISE_REQUIREMENTS), "Requisitos enterprise")
    custom_sources = {
        "description": descripcion,
        "entity": entidad,
        "region": region,
        "origin": origen,
        "status": estado,
    }
    for key, factor in factors.items():
        if not key.startswith("custom_") or not factor.get("enabled"):
            continue
        field = factor.get("field", "description")
        configured_terms = terms(key)
        if field == "amount":
            try:
                matched = float(row.get("monto", 0) or 0) >= float(factor.get("value", 0))
            except Exception:
                matched = False
        else:
            source_text = custom_sources.get(field, descripcion)
            matched = any(term in source_text for term in configured_terms)
        add(key, matched, factor.get("label", "Factor adicional"))
    score = max(0, min(score, 100))
    prioridad = "A" if score >= config["priority_a_min"] else ("B" if score >= config["priority_b_min"] else "C")
    return score, prioridad, ", ".join(motivos)


def enriquecer_oportunidades(df, config=None):
    df = df.copy()
    scores = df.apply(lambda row: calcular_score(row, config), axis=1, result_type="expand")
    df["score"] = scores[0]; df["prioridad"] = scores[1]; df["motivos_score"] = scores[2]
    df["sector"] = df.apply(detectar_sector, axis=1)
    def semaforo(row):
        estado = str(row.get("estado_comercial", "")).lower()
        if "consultas y propuesta" in estado or "consulta y cotiz" in estado: return "🟢"
        if any(value in estado for value in ["vigente para propuesta", "solo para propuesta", "sólo para propuesta", "solo para cotiz", "sólo para cotiz"]): return "🟡"
        if "en evalu" in estado or "revisar" in estado: return "🟠"
        if "cerrado" in estado: return "🔴"
        return row.get("prioridad", "C")
    df["semaforo"] = df.apply(semaforo, axis=1)
    return df
