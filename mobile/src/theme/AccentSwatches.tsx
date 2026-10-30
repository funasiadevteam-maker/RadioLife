// Accent colour picker (mobile) — recolours the app's brand elements.
import React from 'react';
import { View, Pressable, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAppTheme } from './ThemeProvider';
import { ACCENTS, AccentKey } from './tokens';

const ORDER: AccentKey[] = ['violet', 'coral', 'teal', 'amber', 'blue'];

export default function AccentSwatches({ size = 40 }: { size?: number }) {
  const { accent, setAccent } = useAppTheme();
  return (
    <View style={s.row} testID="accent-swatches">
      {ORDER.map((k) => {
        const on = accent === k;
        return (
          <Pressable key={k} testID={`accent-${k}`} onPress={() => setAccent(k)}
            style={[
              s.swatch,
              { width: size, height: size, borderRadius: size / 2, backgroundColor: ACCENTS[k].swatch },
              on && { borderWidth: 3, borderColor: '#fff' },
            ]}>
            {on && <Ionicons name="checkmark" size={Math.round(size * 0.5)} color={ACCENTS[k].onSwatch} />}
          </Pressable>
        );
      })}
    </View>
  );
}

const s = StyleSheet.create({
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, alignItems: 'center' },
  swatch: { alignItems: 'center', justifyContent: 'center' },
});
