import React, { useEffect, useState } from 'react';
import { TouchableOpacity, Image, StyleSheet, Linking, View, Text } from 'react-native';
import { useRouter } from 'expo-router';
import api from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { COLORS, RADIUS, SPACING } from '../constants/theme';

/**
 * AdBanner — serves a real banner from the advertiser banner system for a given
 * zone. Renders NOTHING when no live campaign matches the zone (no empty ad box)
 * or when the user is a paying/premium member (ad-free experience).
 * Fires impression on show and click on tap, then opens the advertiser target URL.
 *
 * Valid zones: landing_hero | station_detail | games | browse_row | wallet |
 *              now_playing | bottom_bar
 */
export default function AdBanner({ zone, country, language, style }: {
  zone: string; country?: string | null; language?: string | null; style?: any;
}) {
  const { user } = useAuth();
  const router = useRouter();
  const isPremium = !!(user?.is_premium || (user?.premium_tier && user.premium_tier !== 'free'));
  const [ad, setAd] = useState<any>(null);

  useEffect(() => {
    if (isPremium) return;           // premium members are ad-free
    let mounted = true;
    (async () => {
      try {
        const params: any = { zone };
        if (country) params.country = country;
        if (language) params.language = language;
        const r = await api.get('/banner/serve', { params });
        const b = r.data?.banner ?? r.data;
        if (mounted && b && b.creative_url) {
          setAd(b);
          api.post('/banner/impression', { banner_id: b.banner_id, zone }).catch(() => {});
        }
      } catch { /* no banner / not eligible */ }
    })();
    return () => { mounted = false; };
  }, [zone, country, language, isPremium]);

  if (isPremium || !ad) return null;

  const onPress = async () => {
    api.post('/banner/click', { banner_id: ad.banner_id, zone }).catch(() => {});
    if (ad.target_url) { try { await Linking.openURL(ad.target_url); } catch { /* */ } }
  };

  return (
    <TouchableOpacity style={[s.wrap, style]} onPress={onPress} activeOpacity={0.9} testID={`ad-banner-${zone}`}>
      <Image source={{ uri: ad.creative_url }} style={s.img} resizeMode="cover" />
      <View style={s.adTag}><Text style={s.adTagText}>AD{ad.cta_text ? ` · ${ad.cta_text}` : ''}</Text></View>
      {ad.store?.has_store && (
        <TouchableOpacity
          style={s.shopChip}
          onPress={() => router.push(ad.store.store_url)}
          testID={`ad-shop-sponsor-${zone}`}
        >
          <Text style={s.shopChipText}>Shop {ad.store.name} ›</Text>
        </TouchableOpacity>
      )}
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  wrap: {
    marginHorizontal: SPACING.md, marginVertical: SPACING.sm,
    borderRadius: RADIUS.lg, overflow: 'hidden',
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  img: { width: '100%', height: 96 },
  adTag: { position: 'absolute', top: 6, right: 6, backgroundColor: 'rgba(0,0,0,0.55)', borderRadius: RADIUS.sm, paddingHorizontal: 6, paddingVertical: 2 },
  adTagText: { color: '#fff', fontSize: 9, fontWeight: '800', letterSpacing: 0.5 },
  shopChip: { position: 'absolute', bottom: 6, right: 6, backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingHorizontal: 10, paddingVertical: 4 },
  shopChipText: { color: '#fff', fontSize: 11, fontWeight: '800' },
});
