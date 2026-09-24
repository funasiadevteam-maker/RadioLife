import React, { useEffect, useState } from 'react';
import { TouchableOpacity, StyleSheet, View, Text, Linking } from 'react-native';
import { Image as ExpoImage } from 'expo-image';
import { useRouter } from 'expo-router';
import api, { BACKEND } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { COLORS, RADIUS, SPACING } from '../constants/theme';

/**
 * BannerAdSlotV2 — mobile renderer for the v2 advertiser banner system
 * (`/api/ads/banner/decision`), the same rotation the web rail uses. Brings
 * the sample local-business banners to mobile inline slots (inline_mpu_1/2).
 *
 * Renders NOTHING when: the user is premium (ad-free), no live campaign
 * matches, the decision is a text-only "house" fallback (no creative), or the
 * creative image fails to load — so a slot never shows a blank box.
 */
const DIMS: Record<string, { w: number; h: number }> = {
  '300x250': { w: 300, h: 250 }, '336x280': { w: 336, h: 280 },
  '250x250': { w: 250, h: 250 }, '320x100': { w: 320, h: 100 },
  '320x50': { w: 320, h: 50 }, '728x90': { w: 728, h: 90 },
  '970x250': { w: 970, h: 250 }, '970x90': { w: 970, h: 90 },
};

export default function BannerAdSlotV2({ slotKey, pageRoute, style }: {
  slotKey: string; pageRoute: string; style?: any;
}) {
  const { user } = useAuth();
  const router = useRouter();
  const isPremium = !!(user?.is_premium
    || (user?.premium_tier && user.premium_tier !== 'free'));
  const [data, setData] = useState<any>(null);
  const [broken, setBroken] = useState(false);

  useEffect(() => {
    if (isPremium) return;
    let alive = true;
    (async () => {
      try {
        const r = await api.get('/ads/banner/decision',
          { params: { slot_key: slotKey, page_route: pageRoute } });
        if (alive) { setBroken(false); setData(r.data); }
      } catch { /* no ad / not eligible */ }
    })();
    return () => { alive = false; };
  }, [slotKey, pageRoute, isPremium]);

  if (isPremium || !data || data.source === 'none') return null;
  const img = data.creative_image_url;
  if (!img || broken) return null;   // house text fallback / broken → hide

  const sizeKey = data.mobile_size || data.size || '300x250';
  const dims = DIMS[sizeKey] || DIMS['300x250'];
  const uri = String(img).startsWith('http') ? img : `${BACKEND}${img}`;

  const onPress = async () => {
    const impId = String(data.impression_pixel || '').split('/').pop();
    api.post('/ads/banner/click',
      { impression_id: impId, click_url: data.click_url }).catch(() => {});
    const url = data.click_url || '';
    if (String(url).startsWith('http')) {
      try { await Linking.openURL(url); } catch { /* */ }
    } else if (url) {
      try { router.push(url as any); } catch { /* route may not exist on mobile */ }
    }
  };

  return (
    <TouchableOpacity style={[s.wrap, style]} onPress={onPress} activeOpacity={0.9}
      testID={`bannerad-v2-${slotKey}`}>
      <ExpoImage source={{ uri }} style={[s.img, { aspectRatio: dims.w / dims.h }]}
        contentFit="cover" transition={200} onError={() => setBroken(true)} />
      <View style={s.adTag}><Text style={s.adTagText}>AD</Text></View>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  wrap: {
    marginHorizontal: SPACING.md, marginVertical: SPACING.sm,
    borderRadius: RADIUS.lg, overflow: 'hidden', alignSelf: 'center',
    width: '100%', maxWidth: 340,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  img: { width: '100%' },
  adTag: {
    position: 'absolute', top: 6, right: 6,
    backgroundColor: 'rgba(0,0,0,0.55)', borderRadius: RADIUS.sm,
    paddingHorizontal: 6, paddingVertical: 2,
  },
  adTagText: { color: '#fff', fontSize: 9, fontWeight: '800', letterSpacing: 0.5 },
});
