import React, { useEffect, useMemo, useRef, useState } from "react";
import { api, AccessProfile, UserCreatePayload, UserRecord } from "../api";
import { Country, CountryFlagIcon, Empty, userInitials } from "../shared";

export const emptyUserForm: UserCreatePayload = {
  email: "",
  password: "",
  first_name: "",
  last_name: "",
  position: "",
  address: "",
  phone_peru: "",
  phone_chile: "",
  access_profile: "peru",
  role: "viewer",
};

export const accessProfileOptions: Array<{ value: AccessProfile; title: string; description: string; flags: Country[] }> = [
  { value: "peru", title: "Perfil Perú", description: "Inicio Perú, Oportunidades Perú y alertas", flags: ["Peru"] },
  { value: "chile", title: "Perfil Chile", description: "Inicio Chile, Oportunidades Chile y alertas", flags: ["Chile"] },
  { value: "both", title: "Perú y Chile", description: "Acceso operativo a los módulos de ambos países", flags: ["Peru", "Chile"] },
];

export function profileName(profile: AccessProfile) {
  return profile === "both" ? "Perú y Chile" : profile === "chile" ? "Chile" : "Perú";
}

export function userLocalPhone(value: string, countryCode: "51" | "56") {
  const digits = value.replace(/\D/g, "");
  const localDigits = digits.startsWith(countryCode) && digits.length > 9 ? digits.slice(countryCode.length) : digits;
  return localDigits.slice(0, 9);
}

export function userInternationalPhone(value: string, countryCode: "51" | "56") {
  const localDigits = userLocalPhone(value, countryCode);
  return localDigits ? `+${countryCode}${localDigits}` : "";
}

export function Users({ token, currentUserId }: { token: string; currentUserId: number }) {
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [form, setForm] = useState<UserCreatePayload>(emptyUserForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [updatingId, setUpdatingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const formRef = useRef<HTMLFormElement>(null);

  async function loadUsers() {
    setLoading(true);
    setError("");
    try {
      setUsers(await api.users(token));
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cargar la lista de usuarios");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadUsers();
  }, [token]);

  function updateField<K extends keyof UserCreatePayload>(field: K, value: UserCreatePayload[K]) {
    setForm((current) => ({ ...current, [field]: value }));
    setError("");
    setSuccess("");
  }

  function resetForm() {
    setForm(emptyUserForm);
    setEditingId(null);
    setError("");
    setSuccess("");
  }

  function editUser(user: UserRecord) {
    setEditingId(user.id);
    setForm({
      email: user.email,
      password: "",
      first_name: user.first_name,
      last_name: user.last_name,
      position: user.position,
      address: user.address,
      phone_peru: userLocalPhone(user.phone_peru, "51"),
      phone_chile: userLocalPhone(user.phone_chile, "56"),
      access_profile: user.access_profile,
      role: user.role,
    });
    setError("");
    setSuccess("");
    window.requestAnimationFrame(() => {
      formRef.current?.scrollIntoView({
        block: "start",
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
      });
      formRef.current?.querySelector<HTMLInputElement>('input[name="first-name"]')?.focus({ preventScroll: true });
    });
  }

  async function submitUser(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const normalizedForm: UserCreatePayload = {
        ...form,
        phone_peru: userInternationalPhone(form.phone_peru, "51"),
        phone_chile: userInternationalPhone(form.phone_chile, "56"),
      };
      if (editingId !== null) {
        const { password, ...editableFields } = normalizedForm;
        const updated = await api.updateUser(token, editingId, password ? { ...editableFields, password } : editableFields);
        setUsers((current) => current.map((item) => item.id === updated.id ? updated : item));
        setForm(emptyUserForm);
        setEditingId(null);
        setSuccess(`Los datos de ${updated.full_name} fueron actualizados.`);
        return;
      }
      const created = await api.createUser(token, normalizedForm);
      setUsers((current) => [created, ...current]);
      setForm(emptyUserForm);
      setSuccess(`${created.full_name} fue dado de alta correctamente.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo crear el usuario");
    } finally {
      setSaving(false);
    }
  }

  async function toggleUser(user: UserRecord) {
    setUpdatingId(user.id);
    setError("");
    setSuccess("");
    try {
      const updated = await api.updateUser(token, user.id, { is_active: !user.is_active });
      setUsers((current) => current.map((item) => item.id === updated.id ? updated : item));
      setSuccess(`${updated.full_name} ahora esta ${updated.is_active ? "activo" : "bloqueado"}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo actualizar el usuario");
    } finally {
      setUpdatingId(null);
    }
  }

  const filteredUsers = useMemo(() => {
    const term = search.trim().toLocaleLowerCase("es");
    if (!term) return users;
    return users.filter((user) => [user.full_name, user.email, user.position, profileName(user.access_profile)]
      .some((value) => value.toLocaleLowerCase("es").includes(term)));
  }, [search, users]);

  const needsPeruPhone = form.access_profile === "peru" || form.access_profile === "both";
  const needsChilePhone = form.access_profile === "chile" || form.access_profile === "both";

  return (
    <div className="users-module">
      <section className="users-intro">
        <div>
          <h2>Usuarios y permisos</h2>
          <p>Da de alta al equipo y define exactamente qué operación puede visualizar.</p>
        </div>
        <div className="users-summary" aria-label="Resumen de usuarios">
          <span><b>{users.filter((user) => user.is_active).length}</b> activos</span>
          <span><b>{users.filter((user) => !user.is_active).length}</b> bloqueados</span>
        </div>
      </section>

      <section className="user-layout">
        <form className={`panel user-form ${editingId !== null ? "editing" : ""}`} onSubmit={submitUser} ref={formRef}>
          <div className="user-section-heading">
            <span className="section-icon" aria-hidden="true">{editingId !== null ? "\u270E" : "+"}</span>
            <div>
              <h3>{editingId !== null ? "Editar usuario" : "Nuevo usuario"}</h3>
              <p>{editingId !== null ? "Actualiza sus datos, acceso y permisos." : "Completa los datos para habilitar su acceso."}</p>
            </div>
          </div>

          <fieldset className="profile-fieldset">
            <legend>Perfil de visualización</legend>
            <div className="profile-choice-grid">
              {accessProfileOptions.map((option) => (
                <label className={`profile-choice ${form.access_profile === option.value ? "selected" : ""}`} key={option.value}>
                  <input
                    type="radio"
                    name="access-profile"
                    value={option.value}
                    checked={form.access_profile === option.value}
                    onChange={() => updateField("access_profile", option.value)}
                  />
                  <span className="profile-flags">{option.flags.map((flag) => <CountryFlagIcon country={flag} key={flag} />)}</span>
                  <span><strong>{option.title}</strong><small>{option.description}</small></span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="user-fields">
            <label>Nombres<input name="first-name" required minLength={2} autoComplete="given-name" value={form.first_name} onChange={(event) => updateField("first_name", event.target.value)} placeholder="Ej. Andrea" /></label>
            <label>Apellidos<input required minLength={2} autoComplete="family-name" value={form.last_name} onChange={(event) => updateField("last_name", event.target.value)} placeholder="Ej. Valdivia Rojas" /></label>
            <label className="full-field">Correo corporativo <span className="field-hint">Sera su usuario de acceso</span><input required type="email" autoComplete="email" value={form.email} onChange={(event) => updateField("email", event.target.value)} placeholder="nombre@empresa.com" /></label>
            <label>Posición<input required minLength={2} autoComplete="organization-title" value={form.position} onChange={(event) => updateField("position", event.target.value)} placeholder="Ej. Ejecutivo comercial" /></label>
            <label>Permiso de gestión<select value={form.role} onChange={(event) => updateField("role", event.target.value as UserCreatePayload["role"])}><option value="viewer">Usuario</option><option value="admin">Administrador</option></select></label>
            <label className="full-field">Dirección<input required minLength={4} autoComplete="street-address" value={form.address} onChange={(event) => updateField("address", event.target.value)} placeholder="Dirección de oficina o residencia" /></label>
            {needsPeruPhone ? (
              <label>Celular Perú <span className="required-label">9 dígitos</span>
                <span className="phone-input-group user-phone-input"><b>+51</b><input required type="tel" inputMode="numeric" autoComplete="tel-national" minLength={9} maxLength={9} pattern="[0-9]{9}" title="Ingresa los 9 dígitos del celular de Perú" value={form.phone_peru} onChange={(event) => updateField("phone_peru", event.target.value.replace(/\D/g, "").slice(0, 9))} placeholder="999 999 999" /></span>
              </label>
            ) : null}
            {needsChilePhone ? (
              <label>Celular Chile <span className="required-label">9 dígitos</span>
                <span className="phone-input-group user-phone-input"><b>+56</b><input required type="tel" inputMode="numeric" autoComplete="tel-national" minLength={9} maxLength={9} pattern="[0-9]{9}" title="Ingresa los 9 dígitos del celular de Chile" value={form.phone_chile} onChange={(event) => updateField("phone_chile", event.target.value.replace(/\D/g, "").slice(0, 9))} placeholder="9 9999 9999" /></span>
              </label>
            ) : null}
            <label className={form.access_profile === "both" ? "full-field" : ""}>{editingId !== null ? "Nueva contraseña" : "Contraseña temporal"} <span className="field-hint">{editingId !== null ? "Opcional" : "Mínimo 8 caracteres"}</span><input required={editingId === null} minLength={8} type="password" autoComplete="new-password" value={form.password} onChange={(event) => updateField("password", event.target.value)} placeholder={editingId !== null ? "Dejar vacío para conservarla" : "Crea una contraseña segura"} /></label>
          </div>

          {error ? <div className="notice danger" role="alert">{error}</div> : null}
          {success ? <div className="notice success" role="status">{success}</div> : null}
          <div className="user-form-actions">
            <button className="ghost" type="button" onClick={resetForm} disabled={saving}>{editingId !== null ? "Cancelar" : "Limpiar"}</button>
            <button className="primary" type="submit" disabled={saving}>{saving ? editingId !== null ? "Guardando cambios..." : "Creando usuario..." : editingId !== null ? "Guardar cambios" : "Dar de alta"}</button>
          </div>
        </form>

        <section className="panel user-directory">
          <div className="directory-heading">
            <div><h3>Directorio</h3><p>{users.length} usuarios registrados</p></div>
            <label className="user-search"><span className="sr-only">Buscar usuario</span><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar nombre, correo o posicion" /></label>
          </div>
          {loading ? <div className="user-skeleton" aria-label="Cargando usuarios"><span /><span /><span /></div> : null}
          {!loading ? (
            <div className="user-list">
              {filteredUsers.map((user) => (
                <article className={`user-row ${user.is_active ? "" : "inactive"}`} key={user.id}>
                  <div className="user-avatar">{userInitials(user.full_name)}</div>
                  <div className="user-main">
                    <div className="user-name-line"><strong>{user.full_name}</strong>{user.id === currentUserId ? <span className="self-badge">Tu cuenta</span> : null}</div>
                    <span>{user.email}</span>
                    <small>{user.position || "Posición no registrada"}</small>
                  </div>
                  <div className="user-access">
                    <span className={`profile-badge ${user.access_profile}`}>
                      {user.access_profile !== "chile" ? <CountryFlagIcon country="Peru" /> : null}
                      {user.access_profile !== "peru" ? <CountryFlagIcon country="Chile" /> : null}
                      {profileName(user.access_profile)}
                    </span>
                    <small>{user.role === "admin" ? "Administrador" : "Usuario"}</small>
                  </div>
                  <div className="user-status-area">
                    <span className={`account-status ${user.is_active ? "active" : "blocked"}`}>{user.is_active ? "Activo" : "Bloqueado"}</span>
                    <div className="user-row-actions">
                      <button className="text-action" type="button" disabled={saving || updatingId === user.id} onClick={() => editUser(user)} aria-label={`Editar datos de ${user.full_name}`}>Editar</button>
                      <button className="text-action" type="button" disabled={user.id === currentUserId || updatingId === user.id || saving} onClick={() => toggleUser(user)}>
                        {updatingId === user.id ? "Actualizando..." : user.is_active ? "Bloquear" : "Reactivar"}
                      </button>
                    </div>
                  </div>
                </article>
              ))}
              {!filteredUsers.length ? <Empty text="No encontramos usuarios con ese criterio." /> : null}
            </div>
          ) : null}
        </section>
      </section>
    </div>
  );
}

export default Users;
