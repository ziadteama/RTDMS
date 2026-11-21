import { useShallow } from 'zustand/react/shallow';

import { Choice } from '@/components/controls';
import { Row, Section } from '@/components/list';
import { useT } from '@/i18n';
import { useSettings, type ThemeSetting, type Units } from '@/state/settings';

export function AppSection() {
  const t = useT();
  const s = useSettings(useShallow((x) => ({ units: x.units, theme: x.theme })));
  const set = useSettings((x) => x.set);

  return (
    <Section title={t('settings.app')}>
      <Row
        label={t('settings.units')}
        right={
          <Choice<Units>
            label={t('settings.units')}
            value={s.units}
            options={[
              { value: 'kmh', label: t('common.kmh') },
              { value: 'mph', label: t('common.mph') },
            ]}
            onChange={(v) => set({ units: v })}
          />
        }
      />
      <Row
        label={t('settings.theme')}
        right={
          <Choice<ThemeSetting>
            label={t('settings.theme')}
            value={s.theme}
            options={(['dark', 'light', 'system'] as const).map((v) => ({ value: v, label: t(`settings.theme.${v}`) }))}
            onChange={(v) => set({ theme: v })}
          />
        }
      />
    </Section>
  );
}
