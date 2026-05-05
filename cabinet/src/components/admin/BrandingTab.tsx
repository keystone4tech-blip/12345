import { useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { brandingApi, setCachedBranding } from '../../api/branding';
import { setCachedFullscreenEnabled } from '../../hooks/useTelegramSDK';
import { UploadIcon, TrashIcon, PencilIcon, CheckIcon, CloseIcon } from './icons';
import { Toggle } from './Toggle';
import { BackgroundEditor } from './BackgroundEditor';

interface BrandingTabProps {
  accentColor?: string;
}

export function BrandingTab({ accentColor = '#3b82f6' }: BrandingTabProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [editingName, setEditingName] = useState(false);
  const [newName, setNewName] = useState('');

  // Queries
  const { data: branding } = useQuery({
    queryKey: ['branding'],
    queryFn: brandingApi.getBranding,
  });

  const { data: fullscreenSettings } = useQuery({
    queryKey: ['fullscreen-enabled'],
    queryFn: brandingApi.getFullscreenEnabled,
  });

  const { data: emailAuthSettings } = useQuery({
    queryKey: ['email-auth-enabled'],
    queryFn: brandingApi.getEmailAuthEnabled,
  });

  const { data: giftSettings } = useQuery({
    queryKey: ['gift-enabled'],
    queryFn: brandingApi.getGiftEnabled,
  });

  // Mutations
  const updateBrandingMutation = useMutation({
    mutationFn: brandingApi.updateName,
    onSuccess: (data) => {
      setCachedBranding(data);
      queryClient.invalidateQueries({ queryKey: ['branding'] });
      setEditingName(false);
    },
  });

  const uploadLogoMutation = useMutation({
    mutationFn: brandingApi.uploadLogo,
    onSuccess: (data) => {
      setCachedBranding(data);
      queryClient.invalidateQueries({ queryKey: ['branding'] });
    },
  });

  const deleteLogoMutation = useMutation({
    mutationFn: brandingApi.deleteLogo,
    onSuccess: (data) => {
      setCachedBranding(data);
      queryClient.invalidateQueries({ queryKey: ['branding'] });
    },
  });

  const updateFullscreenMutation = useMutation({
    mutationFn: (enabled: boolean) => brandingApi.updateFullscreenEnabled(enabled),
    onSuccess: (data) => {
      setCachedFullscreenEnabled(data.enabled);
      queryClient.invalidateQueries({ queryKey: ['fullscreen-enabled'] });
    },
  });

  const updateEmailAuthMutation = useMutation({
    mutationFn: (enabled: boolean) => brandingApi.updateEmailAuthEnabled(enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-auth-enabled'] });
    },
  });

  const updateGiftMutation = useMutation({
    mutationFn: (enabled: boolean) => brandingApi.updateGiftEnabled(enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gift-enabled'] });
    },
  });

  const handleLogoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadLogoMutation.mutate(file);
    }
  };

  return (
    <div className="space-y-6">
      {/* Logo & Name */}
      <div className="rounded-2xl border border-dark-700/50 bg-dark-800/50 p-6">
        <h3 className="mb-4 text-lg font-semibold text-dark-100">
          {t('admin.settings.logoAndName')}
        </h3>

        <div className="flex flex-col gap-6 sm:flex-row sm:items-start">
          {/* Logo */}
          <div className="flex flex-col items-center sm:flex-shrink-0 sm:items-start">
            <div
              className="flex h-24 w-24 items-center justify-center overflow-hidden rounded-2xl text-4xl font-bold text-white sm:h-20 sm:w-20 sm:text-3xl"
              style={{
                background: `linear-gradient(135deg, ${accentColor}, ${accentColor}dd)`,
              }}
            >
              {branding?.has_custom_logo ? (
                <img
                  src={brandingApi.getLogoUrl(branding) ?? undefined}
                  alt="Logo"
                  className="h-full w-full object-cover"
                />
              ) : (
                branding?.logo_letter || 'V'
              )}
            </div>

            <div className="mt-3 flex w-full gap-2 sm:w-auto">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={handleLogoUpload}
                className="hidden"
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={uploadLogoMutation.isPending}
                className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-dark-700 px-4 py-2 text-sm text-dark-200 transition-colors hover:bg-dark-600 disabled:opacity-50 sm:px-3 sm:py-2"
              >
                <UploadIcon />
                <span className="sm:hidden">{t('common.upload')}</span>
              </button>
              {branding?.has_custom_logo && (
                <button
                  onClick={() => deleteLogoMutation.mutate()}
                  disabled={deleteLogoMutation.isPending}
                  className="rounded-xl bg-dark-700 px-4 py-2 text-dark-400 transition-colors hover:bg-error-500/20 hover:text-error-400 disabled:opacity-50 sm:px-3 sm:py-2"
                >
                  <TrashIcon />
                </button>
              )}
            </div>
          </div>

          {/* Name */}
          <div className="flex-1">
            <label className="mb-2 block text-sm font-medium text-dark-300">
              {t('admin.settings.projectName')}
            </label>
            {editingName ? (
              <div className="flex flex-wrap gap-2">
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="min-w-0 flex-1 rounded-xl border border-dark-600 bg-dark-700 px-4 py-2 text-dark-100 focus:border-accent-500 focus:outline-none"
                  maxLength={50}
                />
                <div className="flex gap-2">
                  <button
                    onClick={() => updateBrandingMutation.mutate(newName)}
                    disabled={updateBrandingMutation.isPending}
                    className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-500 text-white transition-colors hover:bg-accent-600 disabled:opacity-50"
                  >
                    <CheckIcon />
                  </button>
                  <button
                    onClick={() => setEditingName(false)}
                    className="flex h-10 w-10 items-center justify-center rounded-xl bg-dark-700 text-dark-300 transition-colors hover:bg-dark-600"
                  >
                    <CloseIcon />
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <span className="text-xl font-medium text-dark-100 sm:text-lg">
                  {branding?.name || t('admin.settings.notSpecified')}
                </span>
                <button
                  onClick={() => {
                    setNewName(branding?.name ?? '');
                    setEditingName(true);
                  }}
                  className="rounded-lg p-2 text-dark-400 transition-colors hover:bg-dark-700 hover:text-dark-200"
                >
                  <PencilIcon />
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Animated Background Editor */}
      <div className="rounded-2xl border border-dark-700/50 bg-dark-800/50 p-6">
        <BackgroundEditor />
      </div>

      {/* Fullscreen & Email toggles */}
      <div className="rounded-2xl border border-dark-700/50 bg-dark-800/50 p-6">
        <h3 className="mb-4 text-lg font-semibold text-dark-100">
          {t('admin.settings.interfaceOptions')}
        </h3>

        <div className="space-y-4">
          <div className="flex items-center justify-between rounded-xl bg-dark-700/30 p-4">
            <div>
              <span className="font-medium text-dark-100">
                {t('admin.settings.autoFullscreen')}
              </span>
              <p className="text-sm text-dark-400">{t('admin.settings.autoFullscreenDesc')}</p>
            </div>
            <Toggle
              checked={fullscreenSettings?.enabled ?? false}
              onChange={() =>
                updateFullscreenMutation.mutate(!(fullscreenSettings?.enabled ?? false))
              }
              disabled={updateFullscreenMutation.isPending}
            />
          </div>

          <div className="flex items-center justify-between rounded-xl bg-dark-700/30 p-4">
            <div>
              <span className="font-medium text-dark-100">{t('admin.settings.emailAuth')}</span>
              <p className="text-sm text-dark-400">{t('admin.settings.emailAuthDesc')}</p>
            </div>
            <Toggle
              checked={emailAuthSettings?.enabled ?? true}
              onChange={() => updateEmailAuthMutation.mutate(!(emailAuthSettings?.enabled ?? true))}
              disabled={updateEmailAuthMutation.isPending}
            />
          </div>

          <div className="flex items-center justify-between rounded-xl bg-dark-700/30 p-4">
            <div>
              <span className="font-medium text-dark-100">{t('admin.settings.giftEnabled')}</span>
              <p className="text-sm text-dark-400">{t('admin.settings.giftEnabledDesc')}</p>
            </div>
            <Toggle
              checked={giftSettings?.enabled ?? false}
              onChange={() => updateGiftMutation.mutate(!(giftSettings?.enabled ?? false))}
              disabled={updateGiftMutation.isPending}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
