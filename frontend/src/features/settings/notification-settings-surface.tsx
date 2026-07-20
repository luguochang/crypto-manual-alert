"use client";

import {
  Bell,
  BellOff,
  CircleAlert,
  CircleCheck,
  Eye,
  EyeOff,
  KeyRound,
  LoaderCircle,
  RefreshCw,
  RotateCcw,
  Save,
  ShieldCheck,
  Smartphone,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import {
  getNotificationSettings,
  ProductApiError,
  updateNotificationSettings,
} from "@/lib/api/product-client";
import type { NotificationSettings } from "@/lib/schemas/product-api";

import {
  notificationSettingsErrorMessage,
  prepareNotificationSettingsUpdate,
} from "./notification-settings-state";

export function NotificationSettingsSurface() {
  const [settings, setSettings] = useState<NotificationSettings | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [deviceKey, setDeviceKey] = useState("");
  const [showDeviceKey, setShowDeviceKey] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void getNotificationSettings()
      .then((nextSettings) => {
        if (!active) return;
        setSettings(nextSettings);
        setEnabled(nextSettings.enabled);
        setLoadError(null);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setLoadError(notificationSettingsErrorMessage(
          reason,
          "无法读取通知设置，请稍后重试。",
        ));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function reload() {
    setLoading(true);
    setLoadError(null);
    setFieldError(null);
    setFormError(null);
    setNotice(null);
    try {
      const nextSettings = await getNotificationSettings();
      setSettings(nextSettings);
      setEnabled(nextSettings.enabled);
      setDeviceKey("");
      setShowDeviceKey(false);
    } catch (reason) {
      setLoadError(notificationSettingsErrorMessage(
        reason,
        "无法读取通知设置，请稍后重试。",
      ));
    } finally {
      setLoading(false);
    }
  }

  async function saveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (settings === null || saving) return;

    setFieldError(null);
    setFormError(null);
    setNotice(null);
    const prepared = prepareNotificationSettingsUpdate(settings, enabled, deviceKey);
    if (!prepared.success) {
      setFieldError(prepared.message);
      return;
    }

    setSaving(true);
    try {
      const nextSettings = await updateNotificationSettings(prepared.submission);
      setSettings(nextSettings);
      setEnabled(nextSettings.enabled);
      setDeviceKey("");
      setShowDeviceKey(false);
      setNotice(prepared.replacesDeviceKey
        ? "Bark 设备 key 已替换，通知设置已保存。"
        : `Bark 通知已${nextSettings.enabled ? "启用" : "停用"}。`);
    } catch (reason) {
      const message = notificationSettingsErrorMessage(
        reason,
        "无法保存通知设置，请稍后重试。",
      );
      if (reason instanceof ProductApiError && reason.status === 409) {
        setFieldError(message);
      } else {
        setFormError(message);
      }
    } finally {
      setSaving(false);
    }
  }

  function resetForm() {
    if (settings === null || saving) return;
    setEnabled(settings.enabled);
    setDeviceKey("");
    setShowDeviceKey(false);
    setFieldError(null);
    setFormError(null);
    setNotice(null);
  }

  const normalizedDeviceKey = deviceKey.trim();
  const hasChanges = settings !== null
    && (enabled !== settings.enabled || normalizedDeviceKey.length > 0);
  const keyDescriptionId = fieldError
    ? "notification-device-key-help notification-settings-error"
    : "notification-device-key-help";

  return (
    <div className="work-page settings-page">
      <header className="work-header">
        <div>
          <p className="section-kicker">Settings / Notification destinations</p>
          <h1>通知设置</h1>
          <p>管理当前用户在此工作区内的 Bark 通知目标。</p>
          <Link className="settings-section-link" href="/settings?section=data-lifecycle" prefetch={false}>
            数据与隐私
          </Link>
        </div>
        <span className="boundary-label list-meta-label">
          <ShieldCheck size={17} aria-hidden="true" />
          用户级凭据
        </span>
      </header>

      {loading ? (
        <section className="empty-work-state" aria-live="polite" aria-busy="true">
          <LoaderCircle className="spinning-icon" size={22} aria-hidden="true" />
          <div>
            <h2>正在读取通知设置</h2>
            <p>正在同步当前用户的通知目标。</p>
          </div>
        </section>
      ) : null}

      {!loading && loadError ? (
        <section className="request-error settings-load-error" role="alert">
          <CircleAlert size={20} aria-hidden="true" />
          <div>
            <h2>通知设置读取失败</h2>
            <p>{loadError}</p>
          </div>
          <button className="retry-button" type="button" onClick={() => void reload()}>
            <RefreshCw size={17} aria-hidden="true" />
            重新读取
          </button>
        </section>
      ) : null}

      {notice ? (
        <p className="settings-save-toast" role="status" aria-live="polite">
          <CircleCheck size={16} aria-hidden="true" />
          {notice}
        </p>
      ) : null}

      {!loading && !loadError && settings ? (
        <section className="settings-panel" aria-labelledby="bark-settings-heading">
          <header className="settings-panel-header">
            <span className="settings-channel-icon" aria-hidden="true">
              <Smartphone size={20} />
            </span>
            <div>
              <h2 id="bark-settings-heading">Bark</h2>
              <p>分析完成后发送到你的 iOS 设备。</p>
            </div>
            <span
              className="settings-state"
              data-enabled={settings.enabled}
              aria-label={`Bark 通知当前${settings.enabled ? "已启用" : "已停用"}`}
            >
              {settings.enabled
                ? <Bell size={15} aria-hidden="true" />
                : <BellOff size={15} aria-hidden="true" />}
              {settings.enabled ? "已启用" : "已停用"}
            </span>
          </header>

          <dl className="settings-facts">
            <div>
              <dt>设备 key</dt>
              <dd>{settings.configured ? "已配置" : "未配置"}</dd>
            </div>
            <div>
              <dt>作用域</dt>
              <dd>当前用户</dd>
            </div>
            <div>
              <dt>更新时间</dt>
              <dd>{formatUpdatedAt(settings.updated_at)}</dd>
            </div>
          </dl>

          <form className="settings-form" onSubmit={saveSettings} noValidate>
            <div className="settings-switch-row">
              <div>
                <strong>通知投递</strong>
                <p>停用后保留已配置的设备 key，重新启用时无需再次输入。</p>
              </div>
              <label className="settings-switch">
                <input
                  type="checkbox"
                  role="switch"
                  checked={enabled}
                  disabled={saving}
                  onChange={(event) => {
                    setEnabled(event.target.checked);
                    setFieldError(null);
                    setFormError(null);
                    setNotice(null);
                  }}
                />
                <span className="settings-switch-track" aria-hidden="true"><span /></span>
                <span className="settings-switch-label">{enabled ? "启用" : "停用"}</span>
              </label>
            </div>

            <div className="settings-key-field">
              <label htmlFor="notification-device-key">
                <KeyRound size={16} aria-hidden="true" />
                {settings.configured ? "替换设备 key" : "设备 key"}
              </label>
              <div className="settings-key-control">
                <input
                  id="notification-device-key"
                  type={showDeviceKey ? "text" : "password"}
                  value={deviceKey}
                  maxLength={255}
                  autoComplete="new-password"
                  autoCapitalize="none"
                  autoCorrect="off"
                  spellCheck={false}
                  placeholder="输入完整 Bark 设备 key"
                  aria-describedby={keyDescriptionId}
                  aria-invalid={fieldError ? true : undefined}
                  disabled={saving}
                  onChange={(event) => {
                    setDeviceKey(event.target.value);
                    setFieldError(null);
                    setFormError(null);
                    setNotice(null);
                  }}
                />
                <button
                  type="button"
                  title={showDeviceKey ? "隐藏本次输入" : "显示本次输入"}
                  aria-label={showDeviceKey ? "隐藏本次输入的设备 key" : "显示本次输入的设备 key"}
                  aria-pressed={showDeviceKey}
                  disabled={saving || deviceKey.length === 0}
                  onClick={() => setShowDeviceKey((current) => !current)}
                >
                  {showDeviceKey
                    ? <EyeOff size={17} aria-hidden="true" />
                    : <Eye size={17} aria-hidden="true" />}
                </button>
              </div>
              <p id="notification-device-key-help">
                {settings.configured
                  ? "当前 key 不会回显；留空将保留现有 key。"
                  : "请输入 Bark 服务生成的完整设备 key，至少 8 个字符。"}
              </p>
              {fieldError ? (
                <p className="settings-key-error" id="notification-settings-error" role="alert">
                  <CircleAlert size={16} aria-hidden="true" />
                  {fieldError}
                </p>
              ) : null}
            </div>

            {formError ? (
              <p className="settings-form-message is-error" role="alert">
                <CircleAlert size={16} aria-hidden="true" />
                {formError}
              </p>
            ) : null}
            <div className="settings-actions">
              <button
                className="settings-reset-button"
                type="button"
                disabled={!hasChanges || saving}
                onClick={resetForm}
              >
                <RotateCcw size={16} aria-hidden="true" />
                撤销更改
              </button>
              <button className="submit-button" type="submit" disabled={!hasChanges || saving}>
                {saving
                  ? <LoaderCircle className="spinning-icon" size={17} aria-hidden="true" />
                  : <Save size={17} aria-hidden="true" />}
                {saving ? "正在保存" : "保存设置"}
              </button>
            </div>
          </form>
        </section>
      ) : null}
    </div>
  );
}

function formatUpdatedAt(value: string | null): string {
  if (value === null) return "尚未保存";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}
