"use client";

import { useSearchParams } from "next/navigation";

import { DataLifecycleControls } from "@/features/settings/data-lifecycle-controls";
import { NotificationSettingsSurface } from "@/features/settings/notification-settings-surface";

export default function SettingsPage() {
  const searchParams = useSearchParams();
  return searchParams.get("section") === "data-lifecycle"
    ? <DataLifecycleControls />
    : <NotificationSettingsSurface />;
}
