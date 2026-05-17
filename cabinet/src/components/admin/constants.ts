import { ThemeColors, DEFAULT_THEME_COLORS } from '../../types/theme';

// Tree sidebar types
export interface TreeSubItem {
  id: string;
  categories: string[];
}

export interface TreeGroup {
  id: string;
  icon: string;
  children: TreeSubItem[];
}

export interface SpecialItem {
  id: string;
  icon?: string;
  iconType?: 'star' | null;
}

export interface SettingsTreeConfig {
  specialItems: SpecialItem[];
  groups: TreeGroup[];
}

// Hierarchical settings tree — all 61 backend category keys mapped into 7 groups
export const SETTINGS_TREE: SettingsTreeConfig = {
  specialItems: [
    { id: 'favorites', iconType: 'star' },
    { id: 'branding', icon: '🎨' },
    { id: 'theme', icon: '🌈' },
    { id: 'analytics', icon: '📊' },
    { id: 'buttons', icon: '📱' },
  ],
  groups: [
    {
      id: 'payments',
      icon: '💳',
      children: [
        { id: 'payments_general', categories: ['PAYMENT', 'PAYMENT_VERIFICATION'] },
        { id: 'payments_stars', categories: ['TELEGRAM'] },
        { id: 'payments_yookassa', categories: ['YOOKASSA'] },
        { id: 'payments_cryptobot', categories: ['CRYPTOBOT'] },
        { id: 'payments_cloudpayments', categories: ['CLOUDPAYMENTS'] },
        { id: 'payments_freekassa', categories: ['FREEKASSA'] },
        { id: 'payments_kassa_ai', categories: ['KASSA_AI'] },
        { id: 'payments_platega', categories: ['PLATEGA'] },
        { id: 'payments_pal24', categories: ['PAL24'] },
        { id: 'payments_heleket', categories: ['HELEKET'] },
        { id: 'payments_mulenpay', categories: ['MULENPAY'] },
        { id: 'payments_tribute', categories: ['TRIBUTE'] },
        { id: 'payments_wata', categories: ['WATA'] },
        { id: 'payments_riopay', categories: ['RIOPAY'] },
        { id: 'payments_severpay', categories: ['SEVERPAY'] },
      ],
    },
    {
      id: 'subscriptions',
      icon: '📦',
      children: [
        { id: 'subs_core', categories: ['SUBSCRIPTIONS_CORE'] },
        { id: 'subs_trial', categories: ['TRIAL'] },
        { id: 'subs_pricing', categories: ['SUBSCRIPTION_PRICES'] },
        { id: 'subs_periods', categories: ['PERIODS'] },
        { id: 'subs_traffic', categories: ['TRAFFIC', 'TRAFFIC_PACKAGES'] },
        { id: 'subs_simple', categories: ['SIMPLE_SUBSCRIPTION'] },
        { id: 'subs_autopay', categories: ['AUTOPAY'] },
      ],
    },
    {
      id: 'interface',
      icon: '🖥️',
      children: [
        {
          id: 'iface_general',
          categories: ['INTERFACE', 'INTERFACE_BRANDING', 'INTERFACE_SUBSCRIPTION'],
        },
        { id: 'iface_connect', categories: ['CONNECT_BUTTON'] },
        { id: 'iface_miniapp', categories: ['MINIAPP'] },
        { id: 'iface_happ', categories: ['HAPP'] },
        { id: 'iface_widget', categories: ['TELEGRAM_WIDGET'] },
        { id: 'iface_oidc', categories: ['TELEGRAM_OIDC'] },
        { id: 'iface_skip', categories: ['SKIP'] },
        { id: 'iface_additional', categories: ['ADDITIONAL'] },
      ],
    },
    {
      id: 'users',
      icon: '👥',
      children: [
        { id: 'users_support', categories: ['SUPPORT'] },
        { id: 'users_referral', categories: ['REFERRAL'] },
        { id: 'users_channel', categories: ['CHANNEL'] },
        { id: 'users_localization', categories: ['LOCALIZATION', 'TIMEZONE'] },
        { id: 'users_moderation', categories: ['MODERATION', 'BAN_NOTIFICATIONS'] },
      ],
    },
    {
      id: 'notifications',
      icon: '🔔',
      children: [
        { id: 'notif_user', categories: ['NOTIFICATIONS', 'WEBHOOK_NOTIFICATIONS'] },
        { id: 'notif_admin', categories: ['ADMIN_NOTIFICATIONS'] },
        { id: 'notif_reports', categories: ['ADMIN_REPORTS'] },
      ],
    },
    {
      id: 'database',
      icon: '🗄️',
      children: [
        { id: 'db_general', categories: ['DATABASE'] },
        { id: 'db_postgres', categories: ['POSTGRES'] },
        { id: 'db_sqlite', categories: ['SQLITE'] },
        { id: 'db_redis', categories: ['REDIS'] },
      ],
    },
    {
      id: 'system',
      icon: '⚙️',
      children: [
        { id: 'sys_core', categories: ['CORE', 'DEBUG'] },
        { id: 'sys_remnawave', categories: ['REMNAWAVE'] },
        { id: 'sys_webapi', categories: ['WEB_API', 'EXTERNAL_ADMIN'] },
        { id: 'sys_webhook', categories: ['WEBHOOK'] },
        { id: 'sys_server', categories: ['SERVER_STATUS'] },
        { id: 'sys_monitoring', categories: ['MONITORING'] },
        { id: 'sys_maintenance', categories: ['MAINTENANCE'] },
        { id: 'sys_backup', categories: ['BACKUP'] },
        { id: 'sys_version', categories: ['VERSION'] },
        { id: 'sys_logging', categories: ['LOG'] },
      ],
    },
  ],
};

// Helper: find which group and sub-item a backend category key belongs to
export function findTreeLocation(
  categoryKey: string,
): { groupId: string; subItemId: string } | null {
  for (const group of SETTINGS_TREE.groups) {
    for (const child of group.children) {
      if (child.categories.includes(categoryKey)) {
        return { groupId: group.id, subItemId: child.id };
      }
    }
  }
  return null;
}

// Helper: get all backend category keys for a given sub-item id
export function getCategoriesForSubItem(subItemId: string): string[] {
  for (const group of SETTINGS_TREE.groups) {
    const child = group.children.find((c) => c.id === subItemId);
    if (child) return child.categories;
  }
  return [];
}

// Theme preset type
export interface ThemePreset {
  id: string;
  colors: ThemeColors;
}

// Theme presets
export const THEME_PRESETS: ThemePreset[] = [
  { id: 'standard', colors: DEFAULT_THEME_COLORS },
  {
    id: 'ocean',
    colors: {
      accent: '#0ea5e9',
      darkBackground: '#0c1222',
      darkSurface: '#1e293b',
      darkText: '#f1f5f9',
      darkTextSecondary: '#94a3b8',
      lightBackground: '#e0f2fe',
      lightSurface: '#f0f9ff',
      lightText: '#0c4a6e',
      lightTextSecondary: '#0369a1',
      success: '#22c55e',
      warning: '#f59e0b',
      error: '#ef4444',
    },
  },
  {
    id: 'forest',
    colors: {
      accent: '#22c55e',
      darkBackground: '#0a1a0f',
      darkSurface: '#14532d',
      darkText: '#f0fdf4',
      darkTextSecondary: '#86efac',
      lightBackground: '#dcfce7',
      lightSurface: '#f0fdf4',
      lightText: '#14532d',
      lightTextSecondary: '#166534',
      success: '#22c55e',
      warning: '#f59e0b',
      error: '#ef4444',
    },
  },
  {
    id: 'sunset',
    colors: {
      accent: '#f97316',
      darkBackground: '#1c1009',
      darkSurface: '#2d1a0e',
      darkText: '#fff7ed',
      darkTextSecondary: '#fdba74',
      lightBackground: '#ffedd5',
      lightSurface: '#fff7ed',
      lightText: '#7c2d12',
      lightTextSecondary: '#c2410c',
      success: '#22c55e',
      warning: '#f59e0b',
      error: '#ef4444',
    },
  },
  {
    id: 'violet',
    colors: {
      accent: '#a855f7',
      darkBackground: '#0f0a1a',
      darkSurface: '#1e1b2e',
      darkText: '#faf5ff',
      darkTextSecondary: '#c4b5fd',
      lightBackground: '#f3e8ff',
      lightSurface: '#faf5ff',
      lightText: '#581c87',
      lightTextSecondary: '#7e22ce',
      success: '#22c55e',
      warning: '#f59e0b',
      error: '#ef4444',
    },
  },
  {
    id: 'rose',
    colors: {
      accent: '#f43f5e',
      darkBackground: '#1a0a10',
      darkSurface: '#2d1520',
      darkText: '#fff1f2',
      darkTextSecondary: '#fda4af',
      lightBackground: '#ffe4e6',
      lightSurface: '#fff1f2',
      lightText: '#881337',
      lightTextSecondary: '#be123c',
      success: '#22c55e',
      warning: '#f59e0b',
      error: '#ef4444',
    },
  },
  {
    id: 'midnight',
    colors: {
      accent: '#6366f1',
      darkBackground: '#030712',
      darkSurface: '#111827',
      darkText: '#f9fafb',
      darkTextSecondary: '#9ca3af',
      lightBackground: '#e5e7eb',
      lightSurface: '#f3f4f6',
      lightText: '#111827',
      lightTextSecondary: '#4b5563',
      success: '#22c55e',
      warning: '#f59e0b',
      error: '#ef4444',
    },
  },
  {
    id: 'turquoise',
    colors: {
      accent: '#14b8a6',
      darkBackground: '#0a1614',
      darkSurface: '#134e4a',
      darkText: '#f0fdfa',
      darkTextSecondary: '#5eead4',
      lightBackground: '#ccfbf1',
      lightSurface: '#f0fdfa',
      lightText: '#134e4a',
      lightTextSecondary: '#0f766e',
      success: '#22c55e',
      warning: '#f59e0b',
      error: '#ef4444',
    },
  },
  // ============ PREMIUM THEMES ============
  {
    id: 'cyberpunk',
    colors: {
      accent: '#00ff41',
      darkBackground: '#0a0a0a',
      darkSurface: '#141414',
      darkText: '#e0ffe0',
      darkTextSecondary: '#6bff6b',
      lightBackground: '#e8fbe8',
      lightSurface: '#f4fdf4',
      lightText: '#0a2e0a',
      lightTextSecondary: '#1a5c1a',
      success: '#00ff41',
      warning: '#ffb300',
      error: '#ff1744',
    },
  },
  {
    id: 'aurora',
    colors: {
      accent: '#818cf8',
      darkBackground: '#0f0b2e',
      darkSurface: '#1a1545',
      darkText: '#e8e4ff',
      darkTextSecondary: '#a5b4fc',
      lightBackground: '#e8e4ff',
      lightSurface: '#f5f3ff',
      lightText: '#1e1b4b',
      lightTextSecondary: '#4338ca',
      success: '#34d399',
      warning: '#fbbf24',
      error: '#f87171',
    },
  },
  {
    id: 'gold',
    colors: {
      accent: '#f59e0b',
      darkBackground: '#0c0c0c',
      darkSurface: '#1a1810',
      darkText: '#fef3c7',
      darkTextSecondary: '#d4a34a',
      lightBackground: '#fef3c7',
      lightSurface: '#fffbeb',
      lightText: '#451a03',
      lightTextSecondary: '#92400e',
      success: '#22c55e',
      warning: '#f59e0b',
      error: '#ef4444',
    },
  },
  {
    id: 'frost',
    colors: {
      accent: '#38bdf8',
      darkBackground: '#0b1929',
      darkSurface: '#132f4c',
      darkText: '#e3f2fd',
      darkTextSecondary: '#90caf9',
      lightBackground: '#e3f2fd',
      lightSurface: '#ffffff',
      lightText: '#0d2137',
      lightTextSecondary: '#1565c0',
      success: '#4caf50',
      warning: '#ff9800',
      error: '#f44336',
    },
  },
  {
    id: 'neon',
    colors: {
      accent: '#ff006e',
      darkBackground: '#0d0221',
      darkSurface: '#1a0a3e',
      darkText: '#ffe4f0',
      darkTextSecondary: '#ff80ab',
      lightBackground: '#fce4ec',
      lightSurface: '#fff0f5',
      lightText: '#4a0028',
      lightTextSecondary: '#c2185b',
      success: '#00e676',
      warning: '#ffab00',
      error: '#ff1744',
    },
  },
  {
    id: 'solar',
    colors: {
      accent: '#ef4444',
      darkBackground: '#1a0505',
      darkSurface: '#2d0f0f',
      darkText: '#fef2f2',
      darkTextSecondary: '#fca5a5',
      lightBackground: '#fee2e2',
      lightSurface: '#fef2f2',
      lightText: '#7f1d1d',
      lightTextSecondary: '#b91c1c',
      success: '#22c55e',
      warning: '#f97316',
      error: '#ef4444',
    },
  },
  {
    id: 'lavender',
    colors: {
      accent: '#c084fc',
      darkBackground: '#110d1b',
      darkSurface: '#1e1730',
      darkText: '#f5f0ff',
      darkTextSecondary: '#d8b4fe',
      lightBackground: '#f3e8ff',
      lightSurface: '#faf5ff',
      lightText: '#3b0764',
      lightTextSecondary: '#7c3aed',
      success: '#22c55e',
      warning: '#f59e0b',
      error: '#ef4444',
    },
  },
  {
    id: 'arctic',
    colors: {
      accent: '#22d3ee',
      darkBackground: '#030a10',
      darkSurface: '#0c1b2a',
      darkText: '#ecfeff',
      darkTextSecondary: '#67e8f9',
      lightBackground: '#cffafe',
      lightSurface: '#ecfeff',
      lightText: '#164e63',
      lightTextSecondary: '#0e7490',
      success: '#22c55e',
      warning: '#f59e0b',
      error: '#ef4444',
    },
  },
];
