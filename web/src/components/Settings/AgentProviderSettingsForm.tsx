import { useEffect, useState } from "react";
import { toast } from "react-hot-toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  type AiAgentProviderName,
  type AiAgentProviderSettings,
  getAiAgentProviderSettings,
  testAiAgentProvider,
  updateAiAgentProviderSettings,
} from "@/features/ai/api";
import { useTranslate } from "@/utils/i18n";

type Draft = AiAgentProviderSettings & { api_key: string };

const defaults: Record<AiAgentProviderName, Pick<Draft, "model" | "base_url">> = {
  deterministic: { model: "", base_url: "" },
  openai: { model: "gpt-4o-mini", base_url: "https://api.openai.com/v1" },
  deepseek: { model: "deepseek-v4-pro", base_url: "https://api.deepseek.com" },
  ollama: { model: "llama3.2", base_url: "http://ollama:11434" },
};

const AgentProviderSettingsForm = () => {
  const t = useTranslate();
  const [draft, setDraft] = useState<Draft>();
  const [unavailable, setUnavailable] = useState(false);
  const [busy, setBusy] = useState<"save" | "test" | null>(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getAiAgentProviderSettings(controller.signal)
      .then((settings) => setDraft({ ...settings, api_key: "" }))
      .catch(() => {
        if (!controller.signal.aborted) {
          setUnavailable(true);
        }
      });
    return () => controller.abort();
  }, []);

  if (unavailable) {
    return <p className="text-sm text-muted-foreground">{t("setting.ai.agent-provider-unavailable")}</p>;
  }
  if (!draft) {
    return <p className="text-sm text-muted-foreground">{t("setting.ai.agent-provider-loading")}</p>;
  }

  const updateDraft = (patch: Partial<Draft>) => {
    setDraft((current) => (current ? { ...current, ...patch } : current));
    setDirty(true);
  };

  const selectProvider = (provider: AiAgentProviderName) => {
    updateDraft({
      provider,
      ...defaults[provider],
      api_key: "",
      api_key_set: false,
      api_key_hint: "",
      allow_real_memo_data: provider === "deterministic" ? false : draft.allow_real_memo_data,
    });
  };

  const save = async () => {
    if (draft.enabled && ["openai", "deepseek"].includes(draft.provider) && !draft.api_key_set && !draft.api_key.trim()) {
      toast.error(t("setting.ai.api-key-required"));
      return;
    }
    setBusy("save");
    try {
      const saved = await updateAiAgentProviderSettings({
        version: "agent-provider-config-v1",
        provider: draft.provider,
        model: draft.model.trim(),
        base_url: draft.base_url.trim(),
        ...(draft.api_key.trim() ? { api_key: draft.api_key.trim() } : {}),
        enabled: draft.enabled,
        allow_real_memo_data: draft.provider === "deterministic" ? false : draft.allow_real_memo_data,
      });
      setDraft({ ...saved, api_key: "" });
      setDirty(false);
      toast.success(t("setting.ai.agent-provider-save-success"));
    } catch {
      toast.error(t("setting.ai.agent-provider-save-error"));
    } finally {
      setBusy(null);
    }
  };

  const test = async () => {
    setBusy("test");
    try {
      const result = await testAiAgentProvider();
      toast.success(t("setting.ai.agent-provider-test-success", { latency: result.latency_ms }));
    } catch {
      toast.error(t("setting.ai.agent-provider-test-error"));
    } finally {
      setBusy(null);
    }
  };

  const remote = draft.provider !== "deterministic";
  const requiresKey = draft.provider === "openai" || draft.provider === "deepseek";
  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <div className="grid gap-2">
        <Label htmlFor="agent-provider-type">{t("setting.ai.agent-provider-type")}</Label>
        <Select value={draft.provider} onValueChange={(value) => selectProvider(value as AiAgentProviderName)}>
          <SelectTrigger id="agent-provider-type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(["deterministic", "openai", "deepseek", "ollama"] as const).map((provider) => (
              <SelectItem key={provider} value={provider}>
                {provider}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {remote && (
        <>
          <div className="grid gap-2">
            <Label htmlFor="agent-provider-model">{t("setting.ai.agent-provider-model")}</Label>
            <Input id="agent-provider-model" value={draft.model} onChange={(event) => updateDraft({ model: event.target.value })} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="agent-provider-base-url">{t("setting.ai.agent-provider-base-url")}</Label>
            <Input
              id="agent-provider-base-url"
              value={draft.base_url}
              onChange={(event) => updateDraft({ base_url: event.target.value })}
            />
          </div>
        </>
      )}

      {requiresKey && (
        <div className="grid gap-2">
          <Label htmlFor="agent-provider-api-key">{t("setting.ai.api-key")}</Label>
          <Input
            id="agent-provider-api-key"
            type="password"
            autoComplete="new-password"
            value={draft.api_key}
            placeholder={draft.api_key_set ? t("setting.ai.keep-api-key") : ""}
            onChange={(event) => updateDraft({ api_key: event.target.value })}
          />
          {draft.api_key_set && <p className="text-xs text-muted-foreground">{t("setting.ai.current-key", { key: draft.api_key_hint })}</p>}
        </div>
      )}

      <div className="flex items-center justify-between gap-4 rounded-md border px-3 py-2">
        <div>
          <Label htmlFor="agent-provider-enabled">{t("setting.ai.agent-provider-enabled")}</Label>
          <p className="text-xs text-muted-foreground">{t("setting.ai.agent-provider-enabled-help")}</p>
        </div>
        <Switch id="agent-provider-enabled" checked={draft.enabled} onCheckedChange={(enabled) => updateDraft({ enabled })} />
      </div>

      {remote && (
        <div className="flex items-center justify-between gap-4 rounded-md border border-amber-500/40 px-3 py-2">
          <div>
            <Label htmlFor="agent-provider-consent">{t("setting.ai.agent-provider-consent")}</Label>
            <p className="text-xs text-muted-foreground">{t("setting.ai.agent-provider-consent-help")}</p>
          </div>
          <Switch
            id="agent-provider-consent"
            checked={draft.allow_real_memo_data}
            onCheckedChange={(allow_real_memo_data) => updateDraft({ allow_real_memo_data })}
          />
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        {t("setting.ai.agent-provider-source", { source: draft.source, version: draft.config_version })}
      </p>
      <div className="flex flex-wrap gap-2">
        <Button disabled={!dirty || busy !== null} onClick={save}>
          {busy === "save" ? t("setting.ai.agent-provider-saving") : t("common.save")}
        </Button>
        <Button variant="outline" disabled={dirty || busy !== null || !draft.enabled} onClick={test}>
          {busy === "test" ? t("setting.ai.agent-provider-testing") : t("setting.ai.agent-provider-test")}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">{t("setting.ai.agent-provider-test-help")}</p>
    </div>
  );
};

export default AgentProviderSettingsForm;
