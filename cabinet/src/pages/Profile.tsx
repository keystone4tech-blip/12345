import { useState, useRef, useEffect } from 'react';
import { Link, useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { usePlatform } from '@/platform';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuthStore } from '../store/auth';
import { authApi } from '../api/auth';
import { isValidEmail } from '../utils/validation';
import {
  notificationsApi,
  NotificationSettings,
  NotificationSettingsUpdate,
} from '../api/notifications';
import { usePWAPush } from '../hooks/usePWAPush';
import { referralApi } from '../api/referral';
import { brandingApi, type EmailAuthEnabled } from '../api/branding';
import { UI } from '../config/constants';
import { Card } from '@/components/data-display/Card';
import { Button } from '@/components/primitives/Button';
import { Switch } from '@/components/primitives/Switch';
import { staggerContainer, staggerItem } from '@/components/motion/transitions';
import { InstallPWABanner } from '@/components/InstallPWABanner';

// Icons
const CopyIcon = () => (
  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184"
    />
  </svg>
);

const CheckIcon = () => (
  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
  </svg>
);

const ShareIcon = () => (
  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M7 8l5-5m0 0l5 5m-5-5v12" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M4 15v3a2 2 0 002 2h12a2 2 0 002-2v-3" />
  </svg>
);

const ArrowRightIcon = () => (
  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
  </svg>
);

const PencilIcon = () => (
  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931z"
    />
  </svg>
);

export default function Profile() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);
  const isAdmin = useAuthStore((state) => state.isAdmin);
  const queryClient = useQueryClient();

  // Локальные состояния для карточки Email-авторизации
  const [verificationError, setVerificationError] = useState<string | null>(null);
  const [verificationSuccess, setVerificationSuccess] = useState<string | null>(null);

  // Локальные состояния для тестового пуш-уведомления
  const [testPushError, setTestPushError] = useState<string | null>(null);
  const [testPushSuccess, setTestPushSuccess] = useState<string | null>(null);

  const [copied, setCopied] = useState(false);
  const [botCopied, setBotCopied] = useState(false);

  // Inline email change flow
  const [changeEmailStep, setChangeEmailStep] = useState<'email' | 'code' | 'success' | null>(null);
  const [newEmail, setNewEmail] = useState('');
  const [changeCode, setChangeCode] = useState('');
  const [changeError, setChangeError] = useState<string | null>(null);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [verificationResendCooldown, setVerificationResendCooldown] = useState(0);
  const newEmailInputRef = useRef<HTMLInputElement>(null);
  const codeInputRef = useRef<HTMLInputElement>(null);

  // Referral data
  const { data: referralInfo } = useQuery({
    queryKey: ['referral-info'],
    queryFn: referralApi.getReferralInfo,
  });

  const { data: referralTerms } = useQuery({
    queryKey: ['referral-terms'],
    queryFn: referralApi.getReferralTerms,
  });

  const { data: branding } = useQuery({
    queryKey: ['branding'],
    queryFn: brandingApi.getBranding,
    staleTime: 60000,
  });

  // Check if email auth is enabled
  const { data: emailAuthConfig } = useQuery<EmailAuthEnabled>({
    queryKey: ['email-auth-enabled'],
    queryFn: brandingApi.getEmailAuthEnabled,
    staleTime: 60000,
  });
  const isEmailAuthEnabled = emailAuthConfig?.enabled ?? true;
  const isEmailVerificationEnabled = emailAuthConfig?.verification_enabled ?? true;

  // Build referral link for cabinet
  const referralLink = referralInfo?.referral_code
    ? `${window.location.origin}/login?${referralInfo.referral_code}`
    : '';
  const botReferralLink = referralInfo?.bot_referral_link || '';

  const copyReferralLink = () => {
    if (referralLink) {
      navigator.clipboard.writeText(referralLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const copyBotReferralLink = () => {
    if (botReferralLink) {
      navigator.clipboard.writeText(botReferralLink);
      setBotCopied(true);
      setTimeout(() => setBotCopied(false), 2000);
    }
  };

  const shareReferralLink = (url: string) => {
    if (!url) return;
    const shareText = t('referral.shareMessage', {
      percent: referralInfo?.commission_percent || 0,
      botName: branding?.name || import.meta.env.VITE_APP_NAME || 'Cabinet',
    });

    if (navigator.share) {
      navigator
        .share({
          title: t('referral.title'),
          text: shareText,
          url: url,
        })
        .catch(() => {});
      return;
    }

    const telegramUrl = `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(shareText)}`;
    window.open(telegramUrl, '_blank', 'noopener,noreferrer');
  };

  const resendVerificationMutation = useMutation({
    mutationFn: authApi.resendVerification,
    onSuccess: () => {
      setVerificationSuccess(t('profile.verificationResent'));
      setVerificationError(null);
      setVerificationResendCooldown(UI.RESEND_COOLDOWN_SEC);
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      setVerificationError(err.response?.data?.detail || t('common.error'));
      setVerificationSuccess(null);
    },
  });

  // Email change mutations
  const requestEmailChangeMutation = useMutation({
    mutationFn: (emailAddr: string) => authApi.requestEmailChange(emailAddr),
    onSuccess: async (data) => {
      setChangeError(null);
      if (data.expires_in_minutes === 0) {
        // Unverified email was replaced directly
        setChangeEmailStep('success');
        const updatedUser = await authApi.getMe();
        setUser(updatedUser);
      } else {
        setChangeEmailStep('code');
        setResendCooldown(UI.RESEND_COOLDOWN_SEC);
      }
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      const detail = err.response?.data?.detail;
      if (detail?.includes('already registered') || detail?.includes('already in use')) {
        setChangeError(t('profile.changeEmail.emailAlreadyUsed'));
      } else if (detail?.includes('same as current')) {
        setChangeError(t('profile.changeEmail.sameEmail'));
      } else if (detail?.includes('rate limit') || detail?.includes('too many')) {
        setChangeError(t('profile.changeEmail.tooManyRequests'));
      } else {
        setChangeError(detail || t('common.error'));
      }
    },
  });

  const verifyEmailChangeMutation = useMutation({
    mutationFn: (verificationCode: string) => authApi.verifyEmailChange(verificationCode),
    onSuccess: async () => {
      setChangeError(null);
      setChangeEmailStep('success');
      const updatedUser = await authApi.getMe();
      setUser(updatedUser);
      queryClient.invalidateQueries({ queryKey: ['user'] });
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      const detail = err.response?.data?.detail;
      if (detail?.includes('invalid') || detail?.includes('wrong')) {
        setChangeError(t('profile.changeEmail.invalidCode'));
      } else if (detail?.includes('expired')) {
        setChangeError(t('profile.changeEmail.codeExpired'));
      } else {
        setChangeError(detail || t('common.error'));
      }
    },
  });

  // Resend cooldown timers
  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setInterval(() => {
      setResendCooldown((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [resendCooldown]);

  useEffect(() => {
    if (verificationResendCooldown <= 0) return;
    const timer = setInterval(() => {
      setVerificationResendCooldown((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [verificationResendCooldown]);

  // Auto-focus inputs on step change (skip on Telegram — keyboard hides bottom nav)
  const { platform: profilePlatform } = usePlatform();
  useEffect(() => {
    if (profilePlatform === 'telegram') return;
    const timer = setTimeout(() => {
      if (changeEmailStep === 'email') newEmailInputRef.current?.focus();
      else if (changeEmailStep === 'code') codeInputRef.current?.focus();
    }, 100);
    return () => clearTimeout(timer);
  }, [changeEmailStep, profilePlatform]);

  // Auto-close success after 3s
  useEffect(() => {
    if (changeEmailStep !== 'success') return;
    const timer = setTimeout(() => resetChangeEmail(), 3000);
    return () => clearTimeout(timer);
  }, [changeEmailStep]);

  const resetChangeEmail = () => {
    setChangeEmailStep(null);
    setNewEmail('');
    setChangeCode('');
    setChangeError(null);
    setResendCooldown(0);
  };

  const handleSendChangeCode = () => {
    setChangeError(null);
    if (!newEmail.trim()) {
      setChangeError(t('profile.emailRequired'));
      return;
    }
    if (!isValidEmail(newEmail.trim())) {
      setChangeError(t('profile.invalidEmail'));
      return;
    }
    if (user?.email && newEmail.toLowerCase().trim() === user.email.toLowerCase()) {
      setChangeError(t('profile.changeEmail.sameEmail'));
      return;
    }
    requestEmailChangeMutation.mutate(newEmail.trim());
  };

  const handleVerifyChangeCode = () => {
    setChangeError(null);
    if (!changeCode.trim()) {
      setChangeError(t('profile.changeEmail.enterCode'));
      return;
    }
    if (changeCode.trim().length < 4) {
      setChangeError(t('profile.changeEmail.invalidCode'));
      return;
    }
    verifyEmailChangeMutation.mutate(changeCode.trim());
  };

  const handleResendChangeCode = () => {
    if (resendCooldown > 0) return;
    requestEmailChangeMutation.mutate(newEmail.trim());
  };

  const { data: notificationSettings, isLoading: notificationsLoading } = useQuery({
    queryKey: ['notification-settings'],
    queryFn: notificationsApi.getSettings,
  });

  const updateNotificationsMutation = useMutation({
    mutationFn: notificationsApi.updateSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notification-settings'] });
    },
  });

  const handleNotificationToggle = (key: keyof NotificationSettings, value: boolean) => {
    const update: NotificationSettingsUpdate = { [key]: value };
    updateNotificationsMutation.mutate(update);
  };

  const handleNotificationValue = (key: keyof NotificationSettings, value: number) => {
    const update: NotificationSettingsUpdate = { [key]: value };
    updateNotificationsMutation.mutate(update);
  };

  // Web Push Hook
  const {
    isSupported: isPushSupported,
    isSubscribed: isPushSubscribed,
    permission: pushPermission,
    loading: pushLoading,
    error: pushError,
    subscribe: subscribePush,
    unsubscribe: unsubscribePush,
  } = usePWAPush();

  const [testPushLoading, setTestPushLoading] = useState(false);
  const [showPermissionModal, setShowPermissionModal] = useState(false);

  const handleSubscribePush = async () => {
    if (pushPermission === 'denied') {
      setShowPermissionModal(true);
      return;
    }
    const success = await subscribePush();
    if (success) {
      // Пользователь явно подписался — удаляем флаг явного отключения
      localStorage.removeItem('pwa-push-explicitly-disabled');
    } else if (Notification.permission === 'denied') {
      setShowPermissionModal(true);
    }
  };

  const handleUnsubscribePush = async () => {
    const success = await unsubscribePush();
    if (success) {
      // Пользователь явно отписался — устанавливаем флаг явного отключения,
      // чтобы исключить автоматическую повторную подписку при монтировании AppShell.
      localStorage.setItem('pwa-push-explicitly-disabled', 'true');
    }
  };

  const handleSendTestPush = async () => {
    setTestPushLoading(true);
    try {
      await notificationsApi.sendTestNotification();
      setTestPushSuccess('Тестовое push-уведомление успешно отправлено!');
      setTestPushError(null);
    } catch (err: any) {
      console.error(err);
      const errMsg = err.response?.data?.detail || 'Не удалось отправить тестовое уведомление. Проверьте разрешения.';
      setTestPushError(errMsg);
      setTestPushSuccess(null);
    } finally {
      setTestPushLoading(false);
    }
  };

  return (
    <motion.div
      className="space-y-6"
      variants={staggerContainer}
      initial="initial"
      animate="animate"
    >
      <motion.div variants={staggerItem}>
        <h1 className="text-2xl font-bold text-dark-50 sm:text-3xl">{t('profile.title')}</h1>
      </motion.div>

      {/* User Info Card */}
      <motion.div variants={staggerItem}>
        <Card>
          <h2 className="mb-6 text-lg font-semibold text-dark-100">{t('profile.accountInfo')}</h2>
          <div className="space-y-4">
            <div className="flex items-center justify-between border-b border-dark-800/50 py-3">
              <span className="text-dark-400">{t('profile.telegramId')}</span>
              <span className="font-medium text-dark-100">{user?.telegram_id}</span>
            </div>
            {user?.username && (
              <div className="flex items-center justify-between border-b border-dark-800/50 py-3">
                <span className="text-dark-400">{t('profile.username')}</span>
                <span className="font-medium text-dark-100">@{user.username}</span>
              </div>
            )}
            <div className="flex items-center justify-between border-b border-dark-800/50 py-3">
              <span className="text-dark-400">{t('profile.name')}</span>
              <span className="font-medium text-dark-100">
                {user?.first_name} {user?.last_name}
              </span>
            </div>
            <div className="flex items-center justify-between py-3">
              <span className="text-dark-400">{t('profile.registeredAt')}</span>
              <span className="font-medium text-dark-100">
                {user?.created_at ? new Date(user.created_at).toLocaleDateString() : '-'}
              </span>
            </div>
          </div>
        </Card>
      </motion.div>

      {/* Connected Accounts Link */}
      <motion.div variants={staggerItem}>
        <Card interactive onClick={() => navigate('/profile/accounts')}>
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-dark-100">
                {t('profile.accounts.goToAccounts')}
              </h2>
              <p className="text-sm text-dark-400">{t('profile.accounts.subtitle')}</p>
            </div>
            <svg
              className="h-5 w-5 text-dark-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
            </svg>
          </div>
        </Card>
      </motion.div>

      {/* Referral Link Widget */}
      {referralTerms?.is_enabled && referralLink && (
        <motion.div variants={staggerItem}>
          <Card>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-dark-100">{t('referral.yourLink')}</h2>
              <Link
                to="/referral"
                className="flex items-center gap-1 text-accent-400 transition-colors hover:text-accent-300"
              >
                <span className="text-sm">{t('referral.title')}</span>
                <ArrowRightIcon />
              </Link>
            </div>
            <div className="space-y-4">
              {/* Cabinet Link */}
              <div>
                <div className="mb-1.5 flex items-center gap-2 text-sm font-medium text-dark-300">
                  <svg className="h-4 w-4 text-accent-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                  </svg>
                  {t('referral.cabinetLink', 'Ссылка на личный кабинет')} <span className="text-dark-400 font-normal">(доступен всегда)</span>
                </div>
                <div className="flex flex-col gap-3 sm:flex-row">
                  <div className="flex-1">
                    <input type="text" readOnly value={referralLink} className="input w-full text-sm" />
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={copyReferralLink}
                      className={`btn-primary shrink-0 px-4 ${copied ? 'bg-success-500 hover:bg-success-500' : ''}`}
                    >
                      {copied ? <CheckIcon /> : <CopyIcon />}
                      <span className="ml-2">
                        {copied ? t('referral.copied') : t('referral.copyLink')}
                      </span>
                    </button>
                    <button
                      onClick={() => shareReferralLink(referralLink)}
                      className="btn-secondary flex shrink-0 items-center px-4"
                    >
                      <ShareIcon />
                      <span className="ml-2">{t('referral.shareButton')}</span>
                    </button>
                  </div>
                </div>
              </div>

              {/* Bot Link */}
              {botReferralLink && (
                <div>
                  <div className="mb-1.5 flex items-center gap-2 text-sm font-medium text-dark-300">
                    <svg className="h-4 w-4 text-accent-400" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.892-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z" />
                    </svg>
                    {t('referral.botLink', 'Ссылка на бота')} <span className="text-dark-400 font-normal">(не работает без ВПН)</span>
                  </div>
                  <div className="flex flex-col gap-3 sm:flex-row">
                    <div className="flex-1">
                      <input type="text" readOnly value={botReferralLink} className="input w-full text-sm" />
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={copyBotReferralLink}
                        className={`btn-primary shrink-0 px-4 ${botCopied ? 'bg-success-500 hover:bg-success-500' : ''}`}
                      >
                        {botCopied ? <CheckIcon /> : <CopyIcon />}
                        <span className="ml-2">
                          {botCopied ? t('referral.copied') : t('referral.copyLink')}
                        </span>
                      </button>
                      <button
                        onClick={() => shareReferralLink(botReferralLink)}
                        className="btn-secondary flex shrink-0 items-center px-4"
                      >
                        <ShareIcon />
                        <span className="ml-2">{t('referral.shareButton')}</span>
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
            <p className="mt-4 text-sm text-dark-500">
              {t('referral.shareHint', { percent: referralInfo?.commission_percent || 0 })}
            </p>
          </Card>
        </motion.div>
      )}

      {/* Email Section - only show when email auth is enabled */}
      {isEmailAuthEnabled && (
        <motion.div variants={staggerItem}>
          <Card>
            <h2 className="mb-6 text-lg font-semibold text-dark-100">{t('profile.emailAuth')}</h2>

            {user?.email ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between border-b border-dark-800/50 py-3">
                  <span className="text-dark-400">Email</span>
                  <div className="flex items-center gap-3">
                    <span className="font-medium text-dark-100">{user.email}</span>
                    {user.email_verified ? (
                      <span className="badge-success">{t('profile.verified')}</span>
                    ) : isEmailVerificationEnabled ? (
                      <span className="badge-warning">{t('profile.notVerified')}</span>
                    ) : null}
                  </div>
                </div>

                {!user.email_verified && isEmailVerificationEnabled && (
                  <div className="rounded-linear border border-warning-500/30 bg-warning-500/10 p-4">
                    <p className="mb-4 text-sm text-warning-400">
                      {t('profile.verificationRequired')}
                    </p>
                    <div className="flex items-center gap-3">
                      <Button
                        onClick={() => resendVerificationMutation.mutate()}
                        loading={resendVerificationMutation.isPending}
                        disabled={verificationResendCooldown > 0}
                      >
                        {verificationResendCooldown > 0
                          ? t('profile.resendIn', { seconds: verificationResendCooldown })
                          : t('profile.resendVerification')}
                      </Button>
                      <button
                        onClick={() => setChangeEmailStep('email')}
                        className="text-sm text-accent-400 transition-colors hover:text-accent-300"
                      >
                        {t('profile.changeEmail.button')}
                      </button>
                    </div>
                  </div>
                )}

                {user.email_verified && (
                  <div className="flex items-center justify-between">
                    <p className="text-sm text-dark-400">{t('profile.canLoginWithEmail')}</p>
                    <button
                      onClick={() => setChangeEmailStep('email')}
                      className="flex items-center gap-2 text-sm text-accent-400 transition-colors hover:text-accent-300"
                    >
                      <PencilIcon />
                      <span>{t('profile.changeEmail.button')}</span>
                    </button>
                  </div>
                )}

                {/* Inline email change flow */}
                <AnimatePresence>
                  {changeEmailStep === 'email' && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div className="space-y-3 border-t border-dark-800/50 pt-4">
                        <label className="block text-sm font-medium text-dark-400">
                          {t('profile.changeEmail.newEmail')}
                        </label>
                        <input
                          ref={newEmailInputRef}
                          type="email"
                          value={newEmail}
                          onChange={(e) => setNewEmail(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault();
                              handleSendChangeCode();
                            }
                          }}
                          placeholder="new@email.com"
                          className="input w-full"
                          autoComplete="email"
                        />
                        {changeError && <p className="text-sm text-error-400">{changeError}</p>}
                        <div className="flex items-center gap-3">
                          <Button
                            onClick={handleSendChangeCode}
                            loading={requestEmailChangeMutation.isPending}
                            disabled={!newEmail.trim()}
                          >
                            {t('profile.changeEmail.sendCode')}
                          </Button>
                          <button
                            onClick={resetChangeEmail}
                            className="text-sm text-dark-400 hover:text-dark-200"
                          >
                            {t('common.cancel')}
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  )}

                  {changeEmailStep === 'code' && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div className="space-y-3 border-t border-dark-800/50 pt-4">
                        <div className="rounded-linear border border-accent-500/30 bg-accent-500/10 p-3">
                          <p className="text-sm text-accent-400">
                            {t('profile.changeEmail.codeSentTo', { email: newEmail })}
                          </p>
                        </div>
                        <label className="block text-sm font-medium text-dark-400">
                          {t('profile.changeEmail.verificationCode')}
                        </label>
                        <input
                          ref={codeInputRef}
                          type="text"
                          inputMode="numeric"
                          value={changeCode}
                          onChange={(e) => setChangeCode(e.target.value.replace(/\D/g, ''))}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault();
                              handleVerifyChangeCode();
                            }
                          }}
                          placeholder="000000"
                          maxLength={6}
                          className="input w-full text-center text-2xl tracking-[0.5em]"
                          autoComplete="one-time-code"
                        />
                        {changeError && <p className="text-sm text-error-400">{changeError}</p>}
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <Button
                              onClick={handleVerifyChangeCode}
                              loading={verifyEmailChangeMutation.isPending}
                              disabled={!changeCode.trim()}
                            >
                              {t('profile.changeEmail.verify')}
                            </Button>
                            <button
                              onClick={() => {
                                setChangeEmailStep('email');
                                setChangeCode('');
                                setChangeError(null);
                              }}
                              className="text-sm text-dark-400 hover:text-dark-200"
                            >
                              {t('common.back')}
                            </button>
                          </div>
                          <button
                            onClick={handleResendChangeCode}
                            disabled={resendCooldown > 0 || requestEmailChangeMutation.isPending}
                            className={`text-sm ${resendCooldown > 0 ? 'text-dark-500' : 'text-accent-400 hover:text-accent-300'}`}
                          >
                            {resendCooldown > 0
                              ? t('profile.changeEmail.resendIn', { seconds: resendCooldown })
                              : t('profile.changeEmail.resendCode')}
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  )}

                  {changeEmailStep === 'success' && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div className="border-t border-dark-800/50 pt-4">
                        <div className="flex items-center gap-3 rounded-linear border border-success-500/30 bg-success-500/10 p-4">
                          <CheckIcon />
                          <div>
                            <p className="font-medium text-success-400">
                              {t('profile.changeEmail.success')}
                            </p>
                            <p className="text-sm text-dark-400">{newEmail}</p>
                          </div>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-dark-400">{t('profile.linkEmailDescription')}</p>
                <Button variant="primary" onClick={() => navigate('/profile/accounts')}>
                  {t('profile.linkEmail')}
                </Button>
              </div>
            )}

            {(verificationError || verificationSuccess) && user?.email && (
              <div className="mt-4">
                {verificationError && (
                  <div className="rounded-linear border border-error-500/30 bg-error-500/10 p-4 text-sm text-error-400">
                    {verificationError}
                  </div>
                )}
                {verificationSuccess && (
                  <div className="rounded-linear border border-success-500/30 bg-success-500/10 p-4 text-sm text-success-400">
                    {verificationSuccess}
                  </div>
                )}
              </div>
            )}
          </Card>
        </motion.div>
      )}

      {/* Notification Settings */}
      <motion.div variants={staggerItem}>
        <Card>
          <h2 className="mb-6 text-lg font-semibold text-dark-100">
            {t('profile.notifications.title')}
          </h2>

          {notificationsLoading ? (
            <div className="flex justify-center py-4">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent-500 border-t-transparent" />
            </div>
          ) : notificationSettings ? (
            <div className="space-y-6">
              {/* Subscription Expiry */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium text-dark-100">
                      {t('profile.notifications.subscriptionExpiry')}
                    </p>
                    <p className="text-sm text-dark-400">
                      {t('profile.notifications.subscriptionExpiryDesc')}
                    </p>
                  </div>
                  <Switch
                    checked={notificationSettings.subscription_expiry_enabled}
                    onCheckedChange={(checked) =>
                      handleNotificationToggle('subscription_expiry_enabled', checked)
                    }
                  />
                </div>
                {notificationSettings.subscription_expiry_enabled && (
                  <div className="flex items-center gap-3 pl-4">
                    <span className="text-sm text-dark-400">
                      {t('profile.notifications.daysBeforeExpiry')}
                    </span>
                    <select
                      value={notificationSettings.subscription_expiry_days}
                      onChange={(e) =>
                        handleNotificationValue('subscription_expiry_days', Number(e.target.value))
                      }
                      className="input w-20 py-1"
                    >
                      {[1, 2, 3, 5, 7, 14].map((d) => (
                        <option key={d} value={d}>
                          {d}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              {/* Traffic Warning */}
              <div className="space-y-3 border-t border-dark-800/50 pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium text-dark-100">
                      {t('profile.notifications.trafficWarning')}
                    </p>
                    <p className="text-sm text-dark-400">
                      {t('profile.notifications.trafficWarningDesc')}
                    </p>
                  </div>
                  <Switch
                    checked={notificationSettings.traffic_warning_enabled}
                    onCheckedChange={(checked) =>
                      handleNotificationToggle('traffic_warning_enabled', checked)
                    }
                  />
                </div>
                {notificationSettings.traffic_warning_enabled && (
                  <div className="flex items-center gap-3 pl-4">
                    <span className="text-sm text-dark-400">
                      {t('profile.notifications.atPercent')}
                    </span>
                    <select
                      value={notificationSettings.traffic_warning_percent}
                      onChange={(e) =>
                        handleNotificationValue('traffic_warning_percent', Number(e.target.value))
                      }
                      className="input w-20 py-1"
                    >
                      {[50, 70, 80, 90, 95].map((p) => (
                        <option key={p} value={p}>
                          {p}%
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              {/* Balance Low */}
              <div className="space-y-3 border-t border-dark-800/50 pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium text-dark-100">
                      {t('profile.notifications.balanceLow')}
                    </p>
                    <p className="text-sm text-dark-400">
                      {t('profile.notifications.balanceLowDesc')}
                    </p>
                  </div>
                  <Switch
                    checked={notificationSettings.balance_low_enabled}
                    onCheckedChange={(checked) =>
                      handleNotificationToggle('balance_low_enabled', checked)
                    }
                  />
                </div>
                {notificationSettings.balance_low_enabled && (
                  <div className="flex items-center gap-3 pl-4">
                    <span className="text-sm text-dark-400">
                      {t('profile.notifications.threshold')}
                    </span>
                    <input
                      type="number"
                      value={notificationSettings.balance_low_threshold}
                      onChange={(e) =>
                        handleNotificationValue('balance_low_threshold', Number(e.target.value))
                      }
                      min={0}
                      className="input w-24 py-1"
                    />
                  </div>
                )}
              </div>

              {/* News */}
              <div className="flex items-center justify-between border-t border-dark-800/50 pt-6">
                <div>
                  <p className="font-medium text-dark-100">{t('profile.notifications.news')}</p>
                  <p className="text-sm text-dark-400">{t('profile.notifications.newsDesc')}</p>
                </div>
                <Switch
                  checked={notificationSettings.news_enabled}
                  onCheckedChange={(checked) => handleNotificationToggle('news_enabled', checked)}
                />
              </div>

              {/* Promo Offers */}
              <div className="flex items-center justify-between border-t border-dark-800/50 pt-6">
                <div>
                  <p className="font-medium text-dark-100">
                    {t('profile.notifications.promoOffers')}
                  </p>
                  <p className="text-sm text-dark-400">
                    {t('profile.notifications.promoOffersDesc')}
                  </p>
                </div>
                <Switch
                  checked={notificationSettings.promo_offers_enabled}
                  onCheckedChange={(checked) =>
                    handleNotificationToggle('promo_offers_enabled', checked)
                  }
                />
              </div>
            </div>
          ) : (
            <p className="text-dark-400">{t('profile.notifications.unavailable')}</p>
          )}
        </Card>
      </motion.div>

      {/* PWA Web Push Settings */}
      {isPushSupported && (
        <motion.div variants={staggerItem}>
          <Card>
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-lg font-semibold text-dark-100">
                  Пуш-уведомления на этом устройстве
                </h2>
                <p className="text-sm text-dark-400 mt-1">
                  Получайте мгновенные уведомления об окончании подписки, предупреждениях о трафике и важных событиях прямо на этом устройстве.
                </p>
              </div>
              <Switch
                checked={isPushSubscribed}
                onCheckedChange={(checked) => {
                  if (checked) handleSubscribePush();
                  else handleUnsubscribePush();
                }}
                disabled={pushLoading}
              />
            </div>

            {pushError && (
              <div className="mb-4 rounded-linear border border-error-500/30 bg-error-500/10 p-3 text-sm text-error-400">
                {pushError}
              </div>
            )}

            {testPushError && (
              <div className="mb-4 rounded-linear border border-error-500/30 bg-error-500/10 p-3 text-sm text-error-400">
                {testPushError}
              </div>
            )}

            {testPushSuccess && (
              <div className="mb-4 rounded-linear border border-success-500/30 bg-success-500/10 p-3 text-sm text-success-400">
                {testPushSuccess}
              </div>
            )}

            {isPushSubscribed && isAdmin && (
              <div className="flex items-center justify-between border-t border-dark-800/50 pt-4">
                <span className="text-sm text-dark-400">
                  Хотите проверить доставку уведомлений? (Администратор)
                </span>
                <Button
                  onClick={handleSendTestPush}
                  loading={testPushLoading}
                  variant="secondary"
                  size="sm"
                >
                  Отправить тест-пуш
                </Button>
              </div>
            )}
          </Card>
        </motion.div>
      )}

      {!isPushSupported && (
        <motion.div variants={staggerItem}>
          <Card>
            <h2 className="text-lg font-semibold text-dark-100 mb-2">
              Пуш-уведомления на этом устройстве
            </h2>
            <div className="rounded-linear border border-warning-500/20 bg-warning-500/5 p-4">
              <p className="text-sm text-warning-400">
                Push-уведомления не поддерживаются вашим текущим браузером.
              </p>
              <p className="mt-2 text-xs text-dark-400">
                Примечание для iOS Safari: чтобы включить уведомления, обязательно установите приложение на главный экран (через меню «Поделиться» → «На экран «Домой») и запустите его оттуда.
              </p>
            </div>
          </Card>
        </motion.div>
      )}

      {/* PWA Install Section */}
      <motion.div variants={staggerItem}>
        <InstallPWABanner variant="card" />
      </motion.div>

      {/* Модальное окно при блокировке пуш-уведомлений */}
      <AnimatePresence>
        {showPermissionModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setShowPermissionModal(false)}
              className="absolute inset-0 bg-dark-950/80 backdrop-blur-sm"
            />
            {/* Modal Body */}
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative w-full max-w-md overflow-hidden rounded-2xl border border-dark-800/80 bg-dark-900 p-6 shadow-2xl z-10"
            >
              <div className="flex items-start gap-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-warning-500/10 text-warning-400">
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                  </svg>
                </div>
                <div className="flex-1">
                  <h3 className="text-lg font-semibold text-dark-100">
                    Уведомления заблокированы
                  </h3>
                  <p className="mt-2 text-sm text-dark-300">
                    Вы заблокировали показ уведомлений для нашего сайта в настройках вашего браузера.
                  </p>
                  <p className="mt-2 text-xs text-dark-400">
                    Чтобы включить их, пожалуйста, нажмите на значок «замочка» или «настроек» в адресной строке вашего браузера и разрешите отправку уведомлений для этого сайта.
                  </p>
                </div>
              </div>
              <div className="mt-6 flex justify-end">
                <Button
                  onClick={() => setShowPermissionModal(false)}
                  variant="primary"
                  size="sm"
                >
                  Хорошо, понял
                </Button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
