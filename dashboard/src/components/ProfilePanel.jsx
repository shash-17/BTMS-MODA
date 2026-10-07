import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useToast } from "./ToastNotification";

export default function ProfilePanel({ onClose, sessionStart }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { addToast, notificationsEnabled, toggleNotifications } = useToast();
  const [pwMode, setPwMode] = useState(false);
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [saving, setSaving] = useState(false);

  const sessionAge = sessionStart
    ? Math.floor((Date.now() - sessionStart) / 1000)
    : 0;

  const formatAge = (sec) => {
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  };

  const initials = (user?.username || "??")
    .slice(0, 2)
    .toUpperCase();

  const handleChangePassword = async (e) => {
    e.preventDefault();
    if (newPw !== confirmPw) {
      addToast({ type: "warning", title: "Mismatch", message: "New passwords do not match" });
      return;
    }
    if (newPw.length < 6) {
      addToast({ type: "warning", title: "Too Short", message: "Password must be at least 6 characters" });
      return;
    }
    setSaving(true);
    // Simulated success — real endpoint can be wired later
    await new Promise((r) => setTimeout(r, 800));
    setSaving(false);
    setPwMode(false);
    setCurrentPw(""); setNewPw(""); setConfirmPw("");
    addToast({ type: "success", title: "Password Updated", message: "Your credentials have been changed" });
  };

  const handleLogout = async () => {
    await logout();
    onClose();
    navigate("/login");
  };

  return (
    <>
      <div className="profile-panel-overlay" onClick={onClose} aria-hidden="true" />
      <aside
        className="profile-panel"
        role="dialog"
        aria-label="User profile panel"
        aria-modal="true"
        id="profile-panel"
      >
        {/* Header */}
        <div className="profile-panel-header">
          <span className="profile-panel-title">Operator Profile</span>
          <button className="profile-close-btn" onClick={onClose} aria-label="Close profile panel">
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="profile-panel-body">
          {/* Avatar + name */}
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <div className="profile-avatar">{initials}</div>
            <div>
              <div style={{ fontWeight: 800, fontSize: 16, color: "var(--bw-900)", letterSpacing: "-0.01em" }}>
                {user?.username || "—"}
              </div>
              <div style={{ marginTop: 4 }}>
                <span className={`profile-role-badge ${user?.role || "operator"}`}>
                  {user?.role || "operator"}
                </span>
              </div>
            </div>
          </div>

          {/* Info rows */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="profile-section-divider">Account Details</div>

            <div className="profile-info-row">
              <span className="profile-info-label">Username</span>
              <span className="profile-info-value">{user?.username || "—"}</span>
            </div>

            <div className="profile-info-row">
              <span className="profile-info-label">Email</span>
              <span className="profile-info-value" style={{ fontSize: 11 }}>
                {user?.email || "—"}
              </span>
            </div>

            <div className="profile-info-row">
              <span className="profile-info-label">User ID</span>
              <span className="profile-info-value">#{user?.id ?? "—"}</span>
            </div>

            <div className="profile-info-row">
              <span className="profile-info-label">Session Age</span>
              <span className="profile-info-value">{formatAge(sessionAge)}</span>
            </div>
          </div>

          {/* Preferences */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="profile-section-divider">Preferences</div>
            <div className="profile-info-row">
              <span className="profile-info-label" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ fontSize: 14 }}>🔔</span> Notifications
              </span>
              <button
                id="toggle-notifications-btn"
                className={`notif-toggle${notificationsEnabled ? " notif-toggle--on" : ""}`}
                onClick={toggleNotifications}
                aria-checked={notificationsEnabled}
                role="switch"
                aria-label="Toggle notification popups"
              >
                <span className="notif-toggle-thumb" />
              </button>
            </div>
          </div>

          {/* Change password */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="profile-section-divider">Security</div>

            {!pwMode ? (
              <button
                className="profile-btn primary"
                onClick={() => setPwMode(true)}
                id="change-pw-btn"
              >
                Change Password
              </button>
            ) : (
              <form onSubmit={handleChangePassword} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <input
                  className="profile-input"
                  type="password"
                  placeholder="Current password"
                  value={currentPw}
                  onChange={(e) => setCurrentPw(e.target.value)}
                  required
                  autoFocus
                />
                <input
                  className="profile-input"
                  type="password"
                  placeholder="New password (min 6 chars)"
                  value={newPw}
                  onChange={(e) => setNewPw(e.target.value)}
                  required
                />
                <input
                  className="profile-input"
                  type="password"
                  placeholder="Confirm new password"
                  value={confirmPw}
                  onChange={(e) => setConfirmPw(e.target.value)}
                  required
                />
                <div style={{ display: "flex", gap: 8 }}>
                  <button
                    type="submit"
                    className="profile-btn primary"
                    disabled={saving}
                    style={{ flex: 1, opacity: saving ? 0.7 : 1 }}
                  >
                    {saving ? "Saving…" : "Update"}
                  </button>
                  <button
                    type="button"
                    onClick={() => { setPwMode(false); setCurrentPw(""); setNewPw(""); setConfirmPw(""); }}
                    style={{
                      flex: 1,
                      padding: "10px",
                      background: "transparent",
                      border: "1.5px solid var(--glass-border-bright)",
                      borderRadius: "var(--r-sm)",
                      color: "var(--bw-500)",
                      fontSize: 12,
                      fontWeight: 700,
                      cursor: "pointer",
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </form>
            )}
          </div>

          {/* Logout */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: "auto" }}>
            <div className="profile-section-divider">Session</div>
            <button className="profile-btn danger" onClick={handleLogout} id="profile-logout-btn">
              Sign Out
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
