import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS } from '../constants/theme';

type Option = string | { id: string; label: string };

type Props = {
  options: Option[];
  selected: string[];
  onToggle: (id: string) => void;
  testID?: string;
};

export default function ChipGrid({ options, selected, onToggle, testID }: Props) {
  return (
    <View style={styles.grid} testID={testID}>
      {options.map((o) => {
        const id = typeof o === 'string' ? o : o.id;
        const label = typeof o === 'string' ? o.replace(/_/g, ' ') : o.label;
        const on = selected.includes(id);
        return (
          <TouchableOpacity
            key={id}
            style={[styles.chip, on && styles.chipOn]}
            onPress={() => onToggle(id)}
            testID={`${testID}-${id}`}
            activeOpacity={0.7}
          >
            {on && <Ionicons name="checkmark" size={14} color={COLORS.secondary} style={{ marginRight: 4 }} />}
            <Text style={[styles.chipText, on && styles.chipTextOn]}>{label}</Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: SPACING.sm,
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.sm + 2,
    borderRadius: RADIUS.full,
    borderWidth: 1,
    borderColor: COLORS.surfaceBorder,
    backgroundColor: COLORS.surface,
  },
  chipOn: {
    borderColor: COLORS.secondary,
    backgroundColor: 'rgba(0, 217, 255, 0.1)',
  },
  chipText: {
    color: COLORS.textDim,
    fontSize: FONT.sm,
    textTransform: 'capitalize',
  },
  chipTextOn: {
    color: COLORS.secondary,
    fontWeight: '600',
  },
});
