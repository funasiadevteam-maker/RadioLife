// Delivery address capture — "use my location" (expo-location) or type an
// address; resolves to a jurisdiction (for destination tax) + lat/lng (route).
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, TextInput, ActivityIndicator, Linking } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Location from 'expo-location';
import { COLORS, FONT, RADIUS } from '../constants/theme';
import { reverseGeocode, forwardGeocode } from '../utils/geocode';
import type { DeliveryAddress } from '../stores/useCartStore';

export default function DeliveryAddressCard({
  value, onChange,
}: { value: DeliveryAddress | null; onChange: (a: DeliveryAddress | null) => void }) {
  const [busy, setBusy] = useState(false);
  const [typed, setTyped] = useState('');
  const [err, setErr] = useState<string | null>(null);

  const useMyLocation = async () => {
    setErr(null); setBusy(true);
    try {
      let { status, canAskAgain } = await Location.getForegroundPermissionsAsync();
      if (status !== 'granted') {
        const req = await Location.requestForegroundPermissionsAsync();
        status = req.status; canAskAgain = req.canAskAgain;
      }
      if (status !== 'granted') {
        setErr(canAskAgain ? 'Location permission is needed to find you.' : 'blocked');
        return;
      }
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      const geo = await reverseGeocode(pos.coords.latitude, pos.coords.longitude);
      if (!geo) { setErr("Couldn't resolve your address. Type it instead."); return; }
      onChange(geo);
    } catch {
      setErr("Couldn't get your location. Type your address instead.");
    } finally { setBusy(false); }
  };

  const findTyped = async () => {
    const q = typed.trim();
    if (!q) return;
    setErr(null); setBusy(true);
    try {
      const geo = await forwardGeocode(q);
      if (!geo) { setErr("Address not found. Try adding a city/country."); return; }
      onChange(geo);
    } finally { setBusy(false); }
  };

  if (value) {
    return (
      <View style={s.card} testID="delivery-address">
        <View style={s.rowHead}>
          <Ionicons name="location" size={16} color={COLORS.primary} />
          <Text style={s.title}>Delivery address</Text>
          <TouchableOpacity onPress={() => onChange(null)} testID="delivery-address-change">
            <Text style={s.change}>Change</Text>
          </TouchableOpacity>
        </View>
        <Text style={s.addr} numberOfLines={2} testID="delivery-address-label">{value.label || value.line1}</Text>
        {(value.city || value.state || value.country) && (
          <Text style={s.juris}>{[value.city, value.state, value.country].filter(Boolean).join(', ')} · tax charged at your location</Text>
        )}
      </View>
    );
  }

  return (
    <View style={s.card} testID="delivery-address">
      <View style={s.rowHead}>
        <Ionicons name="location-outline" size={16} color={COLORS.primary} />
        <Text style={s.title}>Where should we deliver?</Text>
      </View>
      <TouchableOpacity style={s.locBtn} onPress={useMyLocation} disabled={busy} testID="delivery-use-location">
        {busy ? <ActivityIndicator color="#fff" size="small" />
          : <><Ionicons name="navigate" size={15} color="#fff" /><Text style={s.locBtnText}>Use my current location</Text></>}
      </TouchableOpacity>
      <Text style={s.or}>or type an address</Text>
      <View style={s.typeRow}>
        <TextInput style={s.input} value={typed} onChangeText={setTyped} placeholder="Street, city, country"
          placeholderTextColor={COLORS.textMuted} testID="delivery-address-input" onSubmitEditing={findTyped} />
        <TouchableOpacity style={s.findBtn} onPress={findTyped} disabled={busy} testID="delivery-address-find">
          <Text style={s.findBtnText}>Find</Text>
        </TouchableOpacity>
      </View>
      {err === 'blocked' ? (
        <TouchableOpacity onPress={() => Linking.openSettings()} testID="delivery-open-settings">
          <Text style={s.errLink}>Location is blocked — open Settings to enable</Text>
        </TouchableOpacity>
      ) : !!err && <Text style={s.err} testID="delivery-address-error">{err}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 12 },
  rowHead: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 },
  title: { flex: 1, color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  change: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '900' },
  addr: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '700' },
  juris: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', marginTop: 4 },
  locBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingVertical: 11 },
  locBtnText: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
  or: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700', textAlign: 'center', marginVertical: 8 },
  typeRow: { flexDirection: 'row', gap: 8 },
  input: { flex: 1, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.sm, fontWeight: '700' },
  findBtn: { backgroundColor: COLORS.text, borderRadius: RADIUS.md, paddingHorizontal: 16, justifyContent: 'center' },
  findBtnText: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
  err: { color: COLORS.red, fontSize: FONT.xs, fontWeight: '800', marginTop: 8 },
  errLink: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '900', marginTop: 8, textDecorationLine: 'underline' },
});
