import React, { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { contrast, isHexColor, safePrimary, SUGGESTED_PRIMARIES, TenantBrand } from "./brand";
import { Button, Card, TextField } from "./components";

const MAX_LOGO_CHARS = 400_000;
const LOGO_BOX = 480; // px: the logo is shown at ~40px high, this keeps it sharp on retina

/** Scales the logo into LOGO_BOX and re-encodes it as PNG (or WebP if PNG is too heavy). */
function encodeLogo(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    if (!/^image\/(png|jpeg|webp)$/.test(file.type)) {
      reject(new Error("Sube una imagen PNG, JPG o WebP."));
      return;
    }
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      const scale = Math.min(1, LOGO_BOX / Math.max(image.width, image.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(image.width * scale));
      canvas.height = Math.max(1, Math.round(image.height * scale));
      canvas.getContext("2d")?.drawImage(image, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      let data = canvas.toDataURL("image/png");
      if (data.length > MAX_LOGO_CHARS) data = canvas.toDataURL("image/webp", 0.9);
      if (data.length > MAX_LOGO_CHARS) reject(new Error("El logo es demasiado pesado; usa una imagen más simple."));
      else resolve(data);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("No se pudo leer la imagen."));
    };
    image.src = url;
  });
}

export function BrandSettings({ token, brand, onBrandUpdated }: {
  token: string;
  brand: TenantBrand;
  onBrandUpdated: (brand: TenantBrand) => void;
}) {
  const [draft, setDraft] = useState<TenantBrand>(brand);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  useEffect(() => setDraft(brand), [brand]);

  const validColor = isHexColor(draft.primary);
  const primary = validColor ? (draft.primary.startsWith("#") ? draft.primary : `#${draft.primary}`) : brand.primary;
  const safe = safePrimary(primary);
  const ratio = contrast(primary, "#ffffff");
  const changed = draft.name !== brand.name || draft.logoUrl !== brand.logoUrl || draft.primary.toLowerCase() !== brand.primary.toLowerCase();

  async function pickLogo(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setError("");
    try {
      const logoUrl = await encodeLogo(file);
      setDraft((current) => ({ ...current, logoUrl }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo cargar el logo.");
    }
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!validColor || draft.name.trim().length < 2) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const saved = await api.updateTenantBrand(token, { name: draft.name.trim(), logoUrl: draft.logoUrl || "", primary });
      onBrandUpdated({ name: saved.name, logoUrl: saved.logoUrl, primary: saved.primary });
      setNotice("Marca actualizada para todos los usuarios.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar la marca.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title="Marca del cliente" subtitle="Logo, nombre y color principal. Señales y urgencias no cambian con la marca.">
      <form className="ui-brand-form" onSubmit={save}>
        <div className="ui-brand-grid">
          <div className="ui-brand-logo-field">
            <span className="ui-field-label">Logo</span>
            <span className="ui-brand-logo-preview">
              {draft.logoUrl ? <img src={draft.logoUrl} alt={`Logo de ${draft.name}`} /> : <span className="ui-muted">Sin logo</span>}
            </span>
            <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" onChange={(event) => void pickLogo(event)} />
            <Button variant="secondary" size="sm" onClick={() => fileRef.current?.click()}>Subir logo</Button>
            <span className="ui-field-hint">PNG, JPG o WebP sobre fondo blanco.</span>
          </div>
          <div className="ui-brand-fields">
            <TextField label="Nombre del cliente" value={draft.name} maxLength={80} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
            <div>
              <span className="ui-field-label">Color principal</span>
              <div className="ui-brand-colors">
                {SUGGESTED_PRIMARIES.map((color) => (
                  <button
                    key={color}
                    type="button"
                    className="ui-brand-swatch"
                    style={{ background: color }}
                    aria-pressed={primary.toLowerCase() === color}
                    aria-label={`Usar ${color}`}
                    onClick={() => setDraft({ ...draft, primary: color })}
                  />
                ))}
                <input
                  type="color"
                  className="ui-brand-picker"
                  value={primary}
                  aria-label="Elegir otro color"
                  onChange={(event) => setDraft({ ...draft, primary: event.target.value })}
                />
                <input
                  className="ui-input ui-brand-hex"
                  value={draft.primary}
                  aria-label="Código hexadecimal"
                  aria-invalid={!validColor}
                  maxLength={7}
                  onChange={(event) => setDraft({ ...draft, primary: event.target.value })}
                />
              </div>
            </div>
            <div className="ui-brand-preview" style={{ "--brand": safe.color } as React.CSSProperties}>
              <span className="ui-brand-preview-btn">Botón principal</span>
              <span className="ui-field-hint">Contraste con texto blanco: {ratio.toFixed(2)}:1</span>
            </div>
            {safe.adjusted ? (
              <div className="notice danger" role="status">
                Este color es muy claro para texto blanco ({ratio.toFixed(2)}:1, mínimo 4.5:1). Se oscurecerá automáticamente a {safe.color}.
              </div>
            ) : null}
          </div>
        </div>
        <div className="ui-brand-actions">
          <Button variant="ghost" disabled={!changed || saving} onClick={() => setDraft(brand)}>Descartar</Button>
          <Button variant="primary" type="submit" disabled={!changed || saving || !validColor || draft.name.trim().length < 2}>
            {saving ? "Guardando…" : "Guardar marca"}
          </Button>
        </div>
        {error ? <div className="notice danger" role="alert">{error}</div> : null}
        {notice ? <div className="notice success" role="status">{notice}</div> : null}
      </form>
    </Card>
  );
}
