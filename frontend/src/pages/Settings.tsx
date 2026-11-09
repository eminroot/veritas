import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { CircleCheck, KeyRound, LogOut, PlugZap, Settings as SettingsIcon, User, UserCog } from "lucide-react";
import { useAuth, type AccountType } from "@/contexts/AuthContext";
import { Page, PageHead, Panel, Rise, Seg, Tag } from "@/components/console/kit";
import { readOrgDraft } from "@/lib/orgDraft";

export default function Settings() {
  const navigate = useNavigate();
  const { user, accountType, setAccountType, api, connectApi, updateName, sendPasswordReset, changePassword, signOut } = useAuth();
  const [name, setName] = useState(user?.displayName ?? "");
  const [pw, setPw] = useState({ current: "", next: "", again: "" });
  const [note, setNote] = useState<{ key: string; tone: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const methods = [user?.hasPassword ? "Email and password" : null, user?.hasGoogle ? "Google" : null].filter(Boolean).join(" · ");

  const saveName = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy("name");
    const { error } = await updateName(name);
    setBusy(null);
    setNote(error ? { key: "name", tone: "error", text: error.message } : { key: "name", tone: "ok", text: "Saved." });
  };

  const reset = async () => {
    if (!user) return;
    setBusy("reset");
    const { error } = await sendPasswordReset(user.email);
    setBusy(null);
    setNote(error ? { key: "reset", tone: "error", text: error.message } : { key: "reset", tone: "ok", text: `A link to set a password is on its way to ${user.email}.` });
  };

  const savePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (pw.next.length < 8) return setNote({ key: "password", tone: "error", text: "Use at least 8 characters." });
    if (pw.next !== pw.again) return setNote({ key: "password", tone: "error", text: "The new passwords do not match." });
    setBusy("password");
    const { error } = await changePassword(pw.current, pw.next);
    setBusy(null);
    if (error) return setNote({ key: "password", tone: "error", text: error.message });
    setPw({ current: "", next: "", again: "" });
    setNote({ key: "password", tone: "ok", text: "Password changed. Your other devices are signed out." });
  };

  const switchType = (t: AccountType) => {
    if (t === accountType) return;
    setAccountType(t);
    if (t === "organisation" && !readOrgDraft(user?.id) && !(api.status === "connected" && api.me.memberships.length)) {
      navigate("/onboarding");
    }
  };

  const say = (key: string) =>
    note?.key === key ? (
      <p className={`v-note v-note--${note.tone}`} role="status">
        {note.text}
      </p>
    ) : null;

  return (
    <Page>
      <PageHead eyebrow="Account" icon={SettingsIcon} title="Settings" sub="Your name, how you sign in, and what you use Veritas for." />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Rise>
          <Panel title="Profile" icon={User}>
            <form className="v-form" onSubmit={saveName}>
              <label className="v-field">
                <span>Name</span>
                <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" autoComplete="name" />
              </label>
              <label className="v-field">
                <span>Email</span>
                <input value={user?.email ?? ""} readOnly aria-readonly="true" />
              </label>
              <div className="v-form__acts">
                <button className="btn btn--primary" disabled={busy === "name" || name === (user?.displayName ?? "")}>
                  {busy === "name" ? "Saving…" : "Save"}
                </button>
                {say("name")}
              </div>
            </form>
          </Panel>
        </Rise>

        <Rise delay={0.04}>
          <Panel title="Sign-in" icon={KeyRound}>
            <dl className="v-deflist">
              <div>
                <dt>Signs in with</dt>
                <dd>{methods || "—"}</dd>
              </div>
              <div>
                <dt>Email</dt>
                <dd>
                  {user?.email}{" "}
                  {user?.hasGoogle ? (
                    <Tag tone="ok" icon={CircleCheck}>
                      Confirmed by Google
                    </Tag>
                  ) : null}
                </dd>
              </div>
            </dl>
            {user?.hasPassword ? (
              <form className="v-form" onSubmit={savePassword}>
                <label className="v-field">
                  <span>Current password</span>
                  <input type="password" autoComplete="current-password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} />
                </label>
                <label className="v-field">
                  <span>New password</span>
                  <input type="password" autoComplete="new-password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} placeholder="At least 8 characters" />
                </label>
                <label className="v-field">
                  <span>Repeat the new password</span>
                  <input type="password" autoComplete="new-password" value={pw.again} onChange={(e) => setPw({ ...pw, again: e.target.value })} />
                </label>
                <div className="v-form__acts">
                  <button className="btn btn--primary" disabled={busy === "password" || !pw.current || !pw.next}>
                    {busy === "password" ? "Saving…" : "Change password"}
                  </button>
                  {say("password")}
                </div>
              </form>
            ) : (
              <>
                <p className="v-prose v-prose--quiet">Your Google account controls this sign-in, with its own password and two-step verification. You can add a Veritas password as well: we email you a link to set one.</p>
                <div className="v-form__acts">
                  <button className="btn btn--ghost" onClick={reset} disabled={busy === "reset"}>
                    {busy === "reset" ? "Sending…" : "Email me a link to set a password"}
                  </button>
                  {say("reset")}
                </div>
              </>
            )}
          </Panel>
        </Rise>

        <Rise delay={0.06}>
          <Panel title="I use Veritas to" icon={UserCog}>
            <Seg<AccountType>
              id="account-type"
              value={accountType ?? "donor"}
              onChange={switchType}
              options={[
                { value: "donor", label: "Donate" },
                { value: "organisation", label: "Raise money for an organisation" },
              ]}
            />
            <p className="v-prose v-prose--quiet" style={{ marginTop: 12 }}>
              Organisation accounts can donate too. Switching to an organisation asks for its details if Veritas does not have them.
            </p>
          </Panel>
        </Rise>

        <Rise delay={0.08}>
          <Panel
            title="Connection to Veritas"
            icon={PlugZap}
            action={
              <Tag tone={api.status === "connected" ? "ok" : api.status === "connecting" ? "lime" : "warn"}>
                {api.status === "connected" ? "Connected" : api.status === "connecting" ? "Connecting" : api.status === "idle" ? "Not connected" : "Offline"}
              </Tag>
            }
          >
            <p className="v-prose v-prose--quiet">
              {api.status === "connected"
                ? "Your account, donations and organisation come from the Veritas API."
                : api.status === "refused"
                  ? api.message
                  : "The app is showing sample data until it can reach the Veritas API."}
            </p>
            {api.status !== "connected" ? (
              <div className="v-form__acts">
                <button className="btn btn--ghost" onClick={() => void connectApi()} disabled={api.status === "connecting"}>
                  Try again
                </button>
              </div>
            ) : null}
          </Panel>
        </Rise>
      </div>

      <Rise delay={0.1}>
        <Panel title="Session" icon={LogOut}>
          <div className="v-form__acts">
            <button
              className="btn btn--ghost"
              onClick={async () => {
                await signOut();
                navigate("/login", { replace: true });
              }}
            >
              <LogOut />
              Sign out
            </button>
          </div>
        </Panel>
      </Rise>
    </Page>
  );
}
