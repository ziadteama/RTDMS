import { Modal, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { radius, spacing, useTheme } from '@/theme';

import { Icon } from './icon';
import { Row, Section } from './list';
import { Text } from './text';

export function ChoiceSheet<T extends string>({ label, value, options, onChange, onClose }: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  onClose: () => void;
}) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <Modal testID="choice-sheet" visible transparent animationType="fade" statusBarTranslucent onRequestClose={onClose}>
      <View style={{ flex: 1, justifyContent: 'flex-end' }} accessibilityViewIsModal>
        <Pressable accessibilityRole="button" accessibilityLabel="Close options" onPress={onClose}
          style={[StyleSheet.absoluteFill, { backgroundColor: colors.scrim }]} />
        <View style={{
          maxHeight: '80%', backgroundColor: colors.background,
          borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
          padding: spacing.lg, paddingBottom: Math.max(insets.bottom, spacing.lg), gap: spacing.md,
        }}>
          <Text variant="headline" accessibilityRole="header">{label}</Text>
          <ScrollView>
            <Section>
              {options.map((option) => (
                <Row key={option.value} label={option.label} accessibilityRole="radio"
                  accessibilityState={{ checked: option.value === value }}
                  onPress={() => { onChange(option.value); onClose(); }}
                  right={option.value === value ? <Icon name="check" color={colors.textSecondary} /> : undefined} />
              ))}
            </Section>
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}
