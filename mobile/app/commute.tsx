import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView,
  ActivityIndicator, SafeAreaView, Alert, RefreshControl, Switch,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS } from '../src/constants/theme';
import api from '../src/api/client';
import { useAuth } from '../src/contexts/AuthContext';

const MODES = ['driver', 'passenger', 'transit'];
const LABELS = [
  'commute', 'home_to_work', 'work_to_home', 'lunch_run', 'errand',
  'club_night', 'concert', 'movie_night', 'gym', 'airport', 'other',
];
const CATEGORIES = [
  { id: 'restaurant', label: 'Restaurants', icon: 'restaurant' as const },
  { id: 'cafe', label: 'Cafés', icon: 'cafe' as const },
  { id: 'fast_food', label: 'Fast food', icon: 'fast-food' as const },
  { id: 'bar', label: 'Bars', icon: 'beer' as const },
  { id: 'mall', label: 'Malls', icon: 'cart' as const },
  { id: 'gym', label: 'Gyms', icon: 'fitness' as const },
];
const KIND_META: Record<string, { icon: string; label: string }> = {
  geo_proximity: { icon: 'location', label: 'Near route' },
  weather_triggered: { icon: 'rainy', label: 'Weather' },
  daypart_triggered: { icon: 'sunny', label: 'Daypart' },
  traffic_triggered: { icon: 'speedometer', label: 'Traffic' },
  destination_arrival: { icon: 'navigate', label: 'Arriving' },
};

function fmtDur(s: number | null | undefined) {
  if (!s && s !== 0) return '—';
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}
function fmtDist(m: number | null | undefined) {
  if (!m) return '—';
  return `${(m / 1000).toFixed(1)} km`;
}

export default function CommuteScreen() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const [savedLocs, setSavedLocs] = useState<any[]>([]);
  const [originText, setOriginText] = useState('');
  const [destText, setDestText] = useState('');
  const [originLatLng, setOriginLatLng] = useState<any>(null);
  const [destLatLng, setDestLatLng] = useState<any>(null);
  const [mode, setMode] = useState('driver');
  const [label, setLabel] = useState('commute');
  const [preview, setPreview] = useState<any>(null);
  const [activeCmt, setActiveCmt] = useState<any>(null);
  const [nearby, setNearby] = useState<any[]>([]);
  const [activeCategory, setActiveCategory] = useState('restaurant');
  const [opps, setOpps] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [handsOff, setHandsOff] = useState(false);
  const [addingLoc, setAddingLoc] = useState(false);
  const [newLocLabel, setNewLocLabel] = useState('');
  const [newLocAddr, setNewLocAddr] = useState('');
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => { if (!authLoading && !user) router.replace('/login'); }, [user, authLoading]);

  const loadSaved = useCallback(async () => {
    try { const r = await api.get('/commute/saved_locations'); setSavedLocs(r.data.items || []); } catch {}
  }, []);
  const loadActive = useCallback(async () => {
    try { const r = await api.get('/commute/active'); setActiveCmt(r.data.active || null); } catch {}
  }, []);

  useEffect(() => { if (!authLoading && user) { loadSaved(); loadActive(); } }, [authLoading, user]);

  /* Heartbeat while commute is active */
  useEffect(() => {
    if (!activeCmt) return;
    if (heartbeatRef.current) clearInterval(heartbeatRef.current);
    heartbeatRef.current = setInterval(async () => {
      try { await api.post(`/commute/${activeCmt.commute_id}/heartbeat`, {}); } catch {}
    }, 60000);
    return () => { if (heartbeatRef.current) clearInterval(heartbeatRef.current); };
  }, [activeCmt]);

  /* Nearby places */
  useEffect(() => {
    if (!activeCmt) { setNearby([]); return; }
    (async () => {
      try {
        const r = await api.get(`/commute/${activeCmt.commute_id}/places_along_route`,
          { params: { radius: 3000, categories: activeCategory, max_detour_minutes: 10 } });
        setNearby(r.data.items || []);
      } catch {}
    })();
  }, [activeCmt, activeCategory]);

  /* Route opportunities */
  useEffect(() => {
    if (!activeCmt) { setOpps([]); return; }
    let mounted = true;
    const fetch = async () => {
      try {
        const r = await api.get(`/commute/${activeCmt.commute_id}/opportunities`);
        if (mounted) setOpps((r.data.items || []).filter((o: any) => !o.selected && o.engagement_type !== 'dismissed'));
      } catch {}
    };
    fetch();
    const id = setInterval(fetch, 30000);
    return () => { mounted = false; clearInterval(id); };
  }, [activeCmt]);

  const pickSaved = (id: string, isOrigin: boolean) => {
    const loc = savedLocs.find(l => l.loc_id === id);
    if (!loc) return;
    if (isOrigin) { setOriginLatLng({ lat: loc.lat, lng: loc.lng }); setOriginText(loc.label); }
    else { setDestLatLng({ lat: loc.lat, lng: loc.lng }); setDestText(loc.label); }
  };

  const geocode = async (text: string, isOrigin: boolean) => {
    if (!text.trim()) return;
    try {
      const r = await api.post('/commute/saved_locations', { label: `__tmp_${Date.now()}`, address: text });
      const loc = r.data;
      api.delete(`/commute/saved_locations/${loc.loc_id}`).catch(() => {});
      const p = { lat: loc.lat, lng: loc.lng };
      if (isOrigin) setOriginLatLng(p); else setDestLatLng(p);
      Alert.alert('Geocoded', `${text} → ${loc.lat.toFixed(4)}, ${loc.lng.toFixed(4)}`);
    } catch { Alert.alert('Error', 'Could not geocode address'); }
  };

  const previewRoute = async () => {
    if (!originLatLng || !destLatLng) return Alert.alert('Error', 'Pick origin and destination first');
    setLoading(true);
    try {
      const r = await api.post('/commute/route_preview', { origin: originLatLng, destination: destLatLng });
      setPreview(r.data);
    } catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Preview failed'); }
    finally { setLoading(false); }
  };

  const startCommute = async () => {
    if (!originLatLng || !destLatLng) return Alert.alert('Error', 'Need origin + destination');
    setLoading(true);
    try {
      const r = await api.post('/commute/start', { origin: originLatLng, destination: destLatLng, mode, label });
      setActiveCmt(r.data);
      setPreview(null);
    } catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Start failed'); }
    finally { setLoading(false); }
  };

  const endCommute = async (abandon = false) => {
    if (!activeCmt) return;
    try {
      await api.post(`/commute/${activeCmt.commute_id}/${abandon ? 'abandon' : 'end'}`);
      setActiveCmt(null); setPreview(null); setOpps([]); setNearby([]);
      Alert.alert(abandon ? 'Abandoned' : 'Complete', abandon ? 'Commute abandoned' : 'Commute complete!');
    } catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || "Couldn't end commute"); }
  };

  const addSavedLoc = async () => {
    if (!newLocLabel || !newLocAddr) return;
    try {
      await api.post('/commute/saved_locations', { label: newLocLabel, address: newLocAddr });
      loadSaved(); setNewLocLabel(''); setNewLocAddr(''); setAddingLoc(false);
    } catch { Alert.alert('Error', 'Save failed'); }
  };
  const delSavedLoc = async (id: string) => {
    try { await api.delete(`/commute/saved_locations/${id}`); loadSaved(); } catch {}
  };
  const dismissOpp = async (oppId: string) => {
    try {
      await api.post(`/route_ads/${oppId}/engage`, { engagement_type: 'dismissed' });
      setOpps(prev => prev.filter(o => o.opp_id !== oppId));
    } catch {}
  };

  const onRefresh = async () => { setRefreshing(true); await Promise.all([loadSaved(), loadActive()]); setRefreshing(false); };

  if (authLoading) return <View style={st.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={st.screen} testID="commute-screen">
      <ScrollView contentContainerStyle={st.scroll} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />}>
        {/* Header */}
        <View style={st.headerRow}>
          <TouchableOpacity onPress={() => router.back()} testID="commute-back-btn" style={st.backBtn}>
            <Ionicons name="chevron-back" size={14} color={COLORS.textDim} />
            <Text style={st.backText}>back to radio</Text>
          </TouchableOpacity>
        </View>
        <Text style={st.title}><Ionicons name="navigate" size={20} color={COLORS.primary} /> Commute</Text>
        <Text style={st.sub}>Live ETA, traffic, weather & nearby places along your drive.</Text>

        {/* ── Plan form (hidden during active commute) ── */}
        {!activeCmt && (
          <View style={st.formCard} testID="commute-form">
            <Text style={st.formTitle}>Plan your commute</Text>

            {/* FROM */}
            <Text style={st.fieldLabel}>FROM</Text>
            <View style={st.inputRow}>
              <TextInput style={[st.input, { flex: 1 }]} value={originText} onChangeText={setOriginText}
                placeholder="Address or pick saved" placeholderTextColor={COLORS.textMuted} testID="origin-input" />
              <TouchableOpacity style={st.geoBtn} onPress={() => geocode(originText, true)} testID="origin-geocode-btn">
                <Text style={st.geoBtnText}>geocode</Text>
              </TouchableOpacity>
            </View>
            {savedLocs.length > 0 && (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 8 }}>
                <View style={st.chipRow}>
                  {savedLocs.map(l => (
                    <TouchableOpacity key={l.loc_id} style={st.locChip} onPress={() => pickSaved(l.loc_id, true)}
                      testID={`origin-chip-${l.loc_id}`}>
                      <Ionicons name={l.label === 'Home' ? 'home' : l.label === 'Work' ? 'briefcase' : 'location'} size={11} color={COLORS.textDim} />
                      <Text style={st.locChipText}>{l.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </ScrollView>
            )}

            {/* TO */}
            <Text style={st.fieldLabel}>TO</Text>
            <View style={st.inputRow}>
              <TextInput style={[st.input, { flex: 1 }]} value={destText} onChangeText={setDestText}
                placeholder="Address or pick saved" placeholderTextColor={COLORS.textMuted} testID="dest-input" />
              <TouchableOpacity style={st.geoBtn} onPress={() => geocode(destText, false)} testID="dest-geocode-btn">
                <Text style={st.geoBtnText}>geocode</Text>
              </TouchableOpacity>
            </View>
            {savedLocs.length > 0 && (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 8 }}>
                <View style={st.chipRow}>
                  {savedLocs.map(l => (
                    <TouchableOpacity key={l.loc_id} style={st.locChip} onPress={() => pickSaved(l.loc_id, false)}
                      testID={`dest-chip-${l.loc_id}`}>
                      <Ionicons name={l.label === 'Home' ? 'home' : l.label === 'Work' ? 'briefcase' : 'location'} size={11} color={COLORS.textDim} />
                      <Text style={st.locChipText}>{l.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </ScrollView>
            )}

            {/* Mode + Label */}
            <View style={st.modeRow}>
              <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                <View style={st.chipRow}>
                  {MODES.map(m => (
                    <TouchableOpacity key={m} style={[st.modeChip, mode === m && st.modeChipActive]}
                      onPress={() => setMode(m)} testID={`mode-${m}`}>
                      <Text style={[st.modeChipText, mode === m && { color: '#fff' }]}>{m}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </ScrollView>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: 6 }}>
                <View style={st.chipRow}>
                  {LABELS.slice(0, 6).map(l => (
                    <TouchableOpacity key={l} style={[st.modeChip, label === l && st.modeChipActive]}
                      onPress={() => setLabel(l)} testID={`label-${l}`}>
                      <Text style={[st.modeChipText, label === l && { color: '#fff' }]}>{l.replace(/_/g, ' ')}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </ScrollView>
            </View>

            {/* Actions */}
            <View style={st.actionRow}>
              <TouchableOpacity style={st.previewBtn} onPress={previewRoute}
                disabled={loading || !originLatLng || !destLatLng} testID="preview-route-btn">
                {loading ? <ActivityIndicator size={12} color={COLORS.textDim} /> : <Ionicons name="eye" size={14} color={COLORS.textDim} />}
                <Text style={st.previewBtnText}>Preview</Text>
              </TouchableOpacity>
              <TouchableOpacity style={st.startBtn} onPress={startCommute}
                disabled={loading || !originLatLng || !destLatLng} testID="start-commute-btn">
                {loading ? <ActivityIndicator size={14} color="#fff" /> : <Ionicons name="navigate" size={14} color="#fff" />}
                <Text style={st.startBtnText}>Start commute</Text>
              </TouchableOpacity>
            </View>

            {/* Preview chips */}
            {preview && (
              <View style={st.previewChips} testID="route-preview-chips">
                <View style={st.chip}><Ionicons name="navigate" size={11} color={COLORS.secondary} /><Text style={st.chipText}>{fmtDur(preview.route?.duration_in_traffic_seconds)}</Text></View>
                <View style={st.chip}><Ionicons name="speedometer" size={11} color={preview.route?.traffic_status === 'heavy' ? COLORS.red : COLORS.green} /><Text style={st.chipText}>{(preview.route?.traffic_status || 'unknown').toUpperCase()}</Text></View>
                {preview.weather && <View style={st.chip}><Ionicons name="cloud" size={11} color={COLORS.textDim} /><Text style={st.chipText}>{Math.round(preview.weather.temp_c)}°C</Text></View>}
                <View style={st.chip}><Ionicons name="location" size={11} color={COLORS.textDim} /><Text style={st.chipText}>{fmtDist(preview.route?.distance_meters)}</Text></View>
              </View>
            )}
          </View>
        )}

        {/* Map placeholder */}
        <View style={st.mapPlaceholder} testID="commute-map">
          <Ionicons name="map" size={36} color={COLORS.textDim} />
          <Text style={st.mapText}>
            {activeCmt ? `Route: ${fmtDist(activeCmt.route_distance_m)} · ${fmtDur(activeCmt.route_duration_in_traffic_s)}`
              : preview ? `Preview: ${fmtDist(preview.route?.distance_meters)} · ${fmtDur(preview.route?.duration_in_traffic_seconds)}`
              : 'Map renders on native device'}
          </Text>
          {(originLatLng || destLatLng) && (
            <Text style={st.mapCoords}>
              {originLatLng ? `From: ${originLatLng.lat.toFixed(3)}, ${originLatLng.lng.toFixed(3)}` : ''}
              {originLatLng && destLatLng ? '  →  ' : ''}
              {destLatLng ? `To: ${destLatLng.lat.toFixed(3)}, ${destLatLng.lng.toFixed(3)}` : ''}
            </Text>
          )}
        </View>

        {/* ── Active commute card ── */}
        {activeCmt && (
          <View style={st.activeCard} testID="active-commute-card">
            <Text style={st.activeEyebrow}>ACTIVE COMMUTE</Text>
            <Text style={st.activeEta}>{fmtDur(activeCmt.route_duration_in_traffic_s)}</Text>
            <View style={st.activeChips}>
              <View style={st.chip}><Ionicons name="speedometer" size={11} color={activeCmt.traffic_status === 'heavy' ? COLORS.red : COLORS.green} /><Text style={st.chipText}>{(activeCmt.traffic_status || 'unknown').toUpperCase()}</Text></View>
              {activeCmt.weather_snapshot && <View style={st.chip}><Ionicons name="cloud" size={11} color={COLORS.textDim} /><Text style={st.chipText}>{Math.round(activeCmt.weather_snapshot.temp_c)}°C</Text></View>}
              <View style={st.chip}><Ionicons name="location" size={11} color={COLORS.textDim} /><Text style={st.chipText}>{fmtDist(activeCmt.route_distance_m)}</Text></View>
            </View>

            {/* Hands-free toggle */}
            <View style={st.handsRow}>
              <Ionicons name="hand-left" size={14} color={handsOff ? COLORS.green : COLORS.textDim} />
              <Text style={st.handsLabel}>Hands-free mode</Text>
              <Switch value={handsOff} onValueChange={setHandsOff}
                trackColor={{ false: COLORS.cardBorder, true: COLORS.green }}
                testID="hands-free-toggle" />
            </View>

            {activeCmt.mode === 'driver' && (
              <View style={st.drivingBanner} testID="driving-banner">
                <Ionicons name="flash" size={13} color={COLORS.gold} />
                <Text style={st.drivingText}>Driving mode on. Game cards save for later.</Text>
              </View>
            )}

            {/* Opportunities */}
            {!handsOff && opps.length > 0 && (
              <View testID="opps-strip">
                <Text style={st.oppEyebrow}><Ionicons name="sparkles" size={11} color={COLORS.gold} /> COMING UP</Text>
                {opps.slice(0, 3).map(o => {
                  const meta = KIND_META[o.kind] || { icon: 'sparkles', label: o.kind };
                  return (
                    <View key={o.opp_id} style={st.oppCard} testID={`route-opp-${o.kind}`}>
                      <View style={st.oppHead}>
                        <View style={st.oppPill}><Ionicons name={meta.icon as any} size={10} color={COLORS.gold} /><Text style={st.oppPillText}>{meta.label}</Text></View>
                        <TouchableOpacity onPress={() => dismissOpp(o.opp_id)} testID={`opp-dismiss-${o.opp_id}`}><Ionicons name="close" size={14} color={COLORS.textDim} /></TouchableOpacity>
                      </View>
                      <Text style={st.oppTitle}>{o.campaign_title}</Text>
                      {o.sponsor_name && <Text style={st.oppSponsor}>by {o.sponsor_name}</Text>}
                      <View style={st.oppChips}>
                        {o.distance_from_route_m != null && <View style={st.chip}><Ionicons name="location" size={10} color={COLORS.textDim} /><Text style={st.chipText}>{o.distance_from_route_m < 1000 ? `${Math.round(o.distance_from_route_m)}m` : `${(o.distance_from_route_m / 1000).toFixed(1)}km`}</Text></View>}
                        {o.extra_drive_time_seconds > 0 && <View style={st.chip}><Ionicons name="navigate" size={10} color={COLORS.textDim} /><Text style={st.chipText}>+{Math.round(o.extra_drive_time_seconds / 60)}m</Text></View>}
                      </View>
                    </View>
                  );
                })}
              </View>
            )}
            {handsOff && opps.length > 0 && (
              <View style={st.voiceTile} testID="voice-summary-tile">
                <Ionicons name="volume-high" size={16} color={COLORS.secondary} />
                <Text style={st.voiceText}>{opps.length} route opportunities saved. Focus on driving.</Text>
              </View>
            )}

            {/* Nearby categories */}
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: SPACING.md }}>
              <View style={st.chipRow} testID="nearby-tabs">
                {CATEGORIES.map(c => (
                  <TouchableOpacity key={c.id} style={[st.catChip, activeCategory === c.id && st.catChipActive]}
                    onPress={() => setActiveCategory(c.id)} testID={`nearby-cat-${c.id}`}>
                    <Ionicons name={c.icon as any} size={12} color={activeCategory === c.id ? '#fff' : COLORS.textDim} />
                    <Text style={[st.catChipText, activeCategory === c.id && { color: '#fff' }]}>{c.label}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </ScrollView>
            <View testID="nearby-list">
              {nearby.length === 0 ? <Text style={st.emptyText}>Nothing nearby right now.</Text> :
                nearby.slice(0, 8).map(p => (
                  <View key={p.place_id} style={st.nearbyRow} testID={`nearby-row-${p.place_id}`}>
                    <View style={{ flex: 1 }}>
                      <Text style={st.nearbyName}>{p.name}</Text>
                      <Text style={st.nearbyAddr}>{p.address} · +{Math.round((p.extra_drive_time_seconds || 0) / 60)} min detour</Text>
                    </View>
                    {p.rating && <View style={st.ratingPill}><Ionicons name="star" size={9} color={COLORS.gold} /><Text style={st.ratingText}>{p.rating}</Text></View>}
                  </View>
                ))}
            </View>

            {/* End / Abandon */}
            <View style={st.actionRow}>
              <TouchableOpacity style={st.previewBtn} onPress={() => endCommute(true)} testID="abandon-btn">
                <Text style={st.previewBtnText}>Abandon</Text>
              </TouchableOpacity>
              <TouchableOpacity style={st.startBtn} onPress={() => endCommute(false)} testID="end-commute-btn">
                <Ionicons name="flag" size={14} color="#fff" />
                <Text style={st.startBtnText}>End commute</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* ── Saved locations panel ── */}
        <View style={st.savedPanel} testID="saved-locs-panel">
          <View style={st.savedHeader}>
            <Text style={st.savedTitle}><Ionicons name="location" size={14} color={COLORS.primary} /> Saved locations</Text>
            <TouchableOpacity onPress={() => setAddingLoc(!addingLoc)} testID="add-saved-btn">
              <Ionicons name="add-circle" size={20} color={COLORS.primary} />
            </TouchableOpacity>
          </View>
          {addingLoc && (
            <View testID="add-saved-form">
              <TextInput style={st.input} value={newLocLabel} onChangeText={setNewLocLabel}
                placeholder="Label (e.g. Gym)" placeholderTextColor={COLORS.textMuted} testID="new-saved-label" />
              <TextInput style={[st.input, { marginTop: 6 }]} value={newLocAddr} onChangeText={setNewLocAddr}
                placeholder="Address" placeholderTextColor={COLORS.textMuted} testID="new-saved-address" />
              <TouchableOpacity style={[st.startBtn, { marginTop: 8 }]} onPress={addSavedLoc}
                disabled={!newLocLabel || !newLocAddr} testID="new-saved-submit">
                <Text style={st.startBtnText}>Save</Text>
              </TouchableOpacity>
            </View>
          )}
          {savedLocs.length === 0 ? <Text style={st.emptyText}>No saved locations yet.</Text> :
            savedLocs.map(l => (
              <View key={l.loc_id} style={st.savedRow} testID={`saved-loc-${l.loc_id}`}>
                <Ionicons name={l.label === 'Home' ? 'home' : l.label === 'Work' ? 'briefcase' : 'location'} size={14} color={COLORS.primary} />
                <View style={{ flex: 1, marginLeft: 10 }}>
                  <Text style={st.savedLabel}>{l.label}</Text>
                  <Text style={st.savedAddr}>{l.formatted_address || `${l.lat.toFixed(3)}, ${l.lng.toFixed(3)}`}</Text>
                </View>
                <TouchableOpacity onPress={() => delSavedLoc(l.loc_id)} testID={`del-saved-${l.loc_id}`}>
                  <Ionicons name="trash" size={14} color={COLORS.red} />
                </TouchableOpacity>
              </View>
            ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: COLORS.bg },
  scroll: { padding: SPACING.md, paddingBottom: 100 },
  headerRow: { marginBottom: SPACING.xs },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  backText: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  title: { color: COLORS.text, fontSize: 24, fontWeight: '900', marginBottom: 4 },
  sub: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: SPACING.md },
  formCard: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.md, borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: SPACING.md },
  formTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '800', marginBottom: SPACING.md },
  fieldLabel: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 2, marginBottom: 4, marginTop: 8 },
  inputRow: { flexDirection: 'row', gap: 8, marginBottom: 4 },
  input: { backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder, borderRadius: RADIUS.md, padding: 12, color: COLORS.text, fontSize: FONT.md },
  geoBtn: { backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.surfaceBorder, paddingHorizontal: 12, borderRadius: RADIUS.md, justifyContent: 'center' },
  geoBtnText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600' },
  chipRow: { flexDirection: 'row', gap: 6 },
  locChip: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: COLORS.surface, paddingHorizontal: 10, paddingVertical: 6, borderRadius: RADIUS.full, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  locChipText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600' },
  modeRow: { marginTop: SPACING.sm },
  modeChip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: RADIUS.full, backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  modeChipActive: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  modeChipText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600' },
  actionRow: { flexDirection: 'row', gap: 8, marginTop: SPACING.md },
  previewBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.cardBorder },
  previewBtnText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600' },
  startBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, borderRadius: RADIUS.md, backgroundColor: COLORS.primary },
  startBtnText: { color: '#fff', fontSize: FONT.sm, fontWeight: '700' },
  previewChips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: SPACING.sm },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: COLORS.surface, paddingHorizontal: 8, paddingVertical: 4, borderRadius: RADIUS.full },
  chipText: { color: COLORS.textDim, fontSize: 10, fontWeight: '700', letterSpacing: 0.5 },
  mapPlaceholder: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.xl, alignItems: 'center', borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: SPACING.md },
  mapText: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: SPACING.sm, textAlign: 'center' },
  mapCoords: { color: COLORS.textMuted, fontSize: FONT.xs, marginTop: 4, textAlign: 'center' },
  activeCard: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.md, borderWidth: 1, borderColor: COLORS.primary, marginBottom: SPACING.md },
  activeEyebrow: { color: COLORS.primary, fontSize: 10, fontWeight: '700', letterSpacing: 2 },
  activeEta: { color: COLORS.text, fontSize: 36, fontWeight: '900', marginVertical: 4 },
  activeChips: { flexDirection: 'row', gap: 6, marginBottom: SPACING.sm },
  handsRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginVertical: SPACING.sm },
  handsLabel: { flex: 1, color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600' },
  drivingBanner: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: 'rgba(253,183,86,0.1)', padding: 10, borderRadius: RADIUS.md, marginBottom: SPACING.sm },
  drivingText: { color: COLORS.gold, fontSize: FONT.xs, fontWeight: '600', flex: 1 },
  oppEyebrow: { color: COLORS.gold, fontSize: 10, fontWeight: '700', letterSpacing: 2, marginBottom: 8 },
  oppCard: { backgroundColor: COLORS.surface, borderRadius: RADIUS.md, padding: SPACING.sm, marginBottom: 6, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  oppHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  oppPill: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: 'rgba(253,183,86,0.15)', paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.full },
  oppPillText: { color: COLORS.gold, fontSize: 9, fontWeight: '700' },
  oppTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '700' },
  oppSponsor: { color: COLORS.textDim, fontSize: FONT.xs },
  oppChips: { flexDirection: 'row', gap: 6, marginTop: 6 },
  voiceTile: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: 'rgba(59,130,246,0.08)', padding: 12, borderRadius: RADIUS.md, marginVertical: SPACING.sm },
  voiceText: { color: COLORS.secondary, fontSize: FONT.sm, fontWeight: '600', flex: 1 },
  catChip: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: RADIUS.full, backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  catChipActive: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  catChipText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600' },
  nearbyRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  nearbyName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '600' },
  nearbyAddr: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 2 },
  ratingPill: { flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: COLORS.surface, paddingHorizontal: 8, paddingVertical: 4, borderRadius: RADIUS.full },
  ratingText: { color: COLORS.gold, fontSize: 10, fontWeight: '700' },
  emptyText: { color: COLORS.textDim, textAlign: 'center', padding: SPACING.lg, fontSize: FONT.sm },
  savedPanel: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.md, borderWidth: 1, borderColor: COLORS.cardBorder },
  savedHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: SPACING.sm },
  savedTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '700' },
  savedRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  savedLabel: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '600' },
  savedAddr: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 2 },
});
