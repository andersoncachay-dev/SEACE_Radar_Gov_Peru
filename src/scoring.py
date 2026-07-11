from .keywords import CORE_KEYWORDS, TARGET_ENTITIES, TARGET_REGIONS, ENTERPRISE_REQUIREMENTS


def contains_any(text, terms):
    t = str(text or "").lower()
    return any(term in t for term in terms)


def detectar_sector(row):
    texto = f"{row.get('entidad','')} {row.get('descripcion','')} {row.get('objeto','')}".lower()
    if any(x in texto for x in ["ugel", "educativa", "colegio", "institucion educativa"]): return "Educacion"
    if any(x in texto for x in ["diresa", "red de salud", "salud", "hospital"]): return "Salud"
    if "gobierno regional" in texto or "gore" in texto: return "Gobierno Regional"
    if any(x in texto for x in ["marina", "ejercito", "ejército", "fuerza aerea", "fuerza aérea", "provias", "mtc"]): return "Infraestructura/Defensa"
    if "bcrp" in texto or "banco central" in texto: return "Banca Publica"
    if "san gaban" in texto or "electrica" in texto or "energ" in texto: return "Energia"
    return "Otros"


def calcular_score(row):
    descripcion = f"{row.get('descripcion','')} {row.get('objeto','')} {row.get('nomenclatura','')} {row.get('area_usuaria','')}".lower()
    entidad = str(row.get("entidad", "")).lower()
    region = str(row.get("region", "")).lower()
    monto = row.get("monto", 0)
    estado = str(row.get("estado_comercial", "")).lower()
    origen = str(row.get("origen", "")).lower()
    score = 0; motivos = []
    if contains_any(descripcion, CORE_KEYWORDS): score += 25; motivos.append("Keyword conectividad/satelital")
    if contains_any(entidad, TARGET_ENTITIES) or "provias" in entidad or "mtc" in entidad: score += 20; motivos.append("Entidad objetivo")
    if any(r == region or r in region for r in TARGET_REGIONS): score += 15; motivos.append("Region priorizada")
    try:
        if float(monto or 0) >= 100000: score += 15; motivos.append("Monto atractivo")
    except Exception: pass
    if "menor_8" in origen: score += 10; motivos.append("Compra rápida menor a 8 UIT")
    if "consultas y propuesta" in estado or "consulta y cotiz" in estado: score += 30; motivos.append("Vigente para consultas/cotización")
    elif "solo para propuesta" in estado or "sólo para propuesta" in estado or "solo para cotiz" in estado or "sólo para cotiz" in estado: score += 20; motivos.append("Vigente solo para propuesta/cotización")
    elif "en evalu" in estado: score += 5; motivos.append("En evaluación")
    elif "cerrado" in estado: score = max(0, score - 35); motivos.append("Proceso cerrado")
    elif "revisar" in estado: motivos.append("Revisar cronograma")
    if contains_any(descripcion, ENTERPRISE_REQUIREMENTS): score += 10; motivos.append("Requisitos enterprise")
    score = min(score, 100)
    prioridad = "A" if score >= 70 else ("B" if score >= 45 else "C")
    return score, prioridad, ", ".join(motivos)


def enriquecer_oportunidades(df):
    df = df.copy()
    scores = df.apply(calcular_score, axis=1, result_type="expand")
    df["score"] = scores[0]; df["prioridad"] = scores[1]; df["motivos_score"] = scores[2]
    df["sector"] = df.apply(detectar_sector, axis=1)
    def semaforo(row):
        estado = str(row.get("estado_comercial", "")).lower()
        if "consultas y propuesta" in estado or "consulta y cotiz" in estado: return "🟢"
        if "solo para propuesta" in estado or "sólo para propuesta" in estado or "solo para cotiz" in estado or "sólo para cotiz" in estado: return "🟡"
        if "en evalu" in estado or "revisar" in estado: return "🟠"
        if "cerrado" in estado: return "🔴"
        return row.get("prioridad", "C")
    df["semaforo"] = df.apply(semaforo, axis=1)
    return df
