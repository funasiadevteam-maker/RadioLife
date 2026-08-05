import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Linking, ViewStyle } from 'react-native';
import { COLORS, SPACING, FONT } from '../constants/theme';

const URL = 'https://funasianetwork.com';

export default function FunAsiaFooter({ style }: { style?: ViewStyle }) {
  return (
    <View style={[s.wrap, style]} testID="funasia-footer">
      <Text style={s.text}>part of </Text>
      <TouchableOpacity onPress={() => Linking.openURL(URL)} testID="funasia-footer-link" hitSlop={{ top: 8, bottom: 8, left: 4, right: 8 }}>
        <Text style={s.link}>funasianetwork.com</Text>
      </TouchableOpacity>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: SPACING.md },
  text: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  link: { color: COLORS.secondary, fontSize: FONT.xs, fontWeight: '800', textDecorationLine: 'underline' },
});
