from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select

from .database import SessionLocal
from .models import AppSetting, Opportunity


REGIONS = {
    "4737-3-LE26": "Libertador General Bernardo O'Higgins",
    "3540-5-L126": "Aysén del General Carlos Ibáñez del Campo",
    "3542-18-LE25": "Magallanes y de la Antártica Chilena",
    "3637-26-LP25": "Magallanes y de la Antártica Chilena",
    "2790-65-L125": "Región Metropolitana de Santiago",
    "3542-1-LE25": "Magallanes y de la Antártica Chilena",
    "1410-43-L124": "Antofagasta",
    "3371-11-LE24": "Libertador General Bernardo O'Higgins",
    "1142-12-L124": "Maule",
    "3737-20-L124": "Biobío",
    "3838-57-LP26": "Libertador General Bernardo O'Higgins",
    "1747-37-L126": "Antofagasta",
    "2775-64-CO26": "Libertador General Bernardo O'Higgins",
    "702988-16-LE26": "Magallanes y de la Antártica Chilena",
    "3542-11-LE26": "Magallanes y de la Antártica Chilena",
    "702988-13-L126": "Magallanes y de la Antártica Chilena",
    "1057432-13-R226": "Biobío",
    "1057432-13-R126": "Biobío",
    "1057432-13-L126": "Biobío",
    "2778-7-LE26": "Libertador General Bernardo O'Higgins",
    "788110-4-L126": "Libertador General Bernardo O'Higgins",
    "3542-16-LE26": "Magallanes y de la Antártica Chilena",
    "702988-12-LE26": "Magallanes y de la Antártica Chilena",
    "702988-20-LE26": "Magallanes y de la Antártica Chilena",
    "702988-19-LE26": "Magallanes y de la Antártica Chilena",
    "948-17-L126": "Región Metropolitana de Santiago",
    "5048-11-O126": "Región Metropolitana de Santiago",
    "5048-12-O126": "Libertador General Bernardo O'Higgins",
    "5048-10-O126": "Coquimbo",
}


def main() -> None:
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(Opportunity).where(
                Opportunity.source.like("mercado_publico%"),
                Opportunity.external_id.in_(REGIONS),
            )
        ).all()
        changes = []
        for item in rows:
            previous = item.region
            item.region = REGIONS[item.external_id]
            changes.append({"id": item.id, "external_id": item.external_id, "previous_region": previous, "new_region": item.region})
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        audit = {
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "source": "MercadoPublico.cl, organismo comprador y ubicación oficial",
            "expected": len(REGIONS),
            "updated": len(changes),
            "changes": changes,
        }
        db.add(AppSetting(key=f"audit.chile_region_manual.{stamp}", value=json.dumps(audit, ensure_ascii=False)))
        db.commit()
        print(json.dumps(audit, ensure_ascii=False))
        if len(changes) != len(REGIONS):
            raise SystemExit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
