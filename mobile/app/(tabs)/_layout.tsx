import { Tabs, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useThemeTokens } from '../../src/theme/ThemeProvider';
import type { ThemeTokens } from '../../src/theme/tokens';

function ScanPayFab() {
  const router = useRouter();
  const t = useThemeTokens();
  const f = fabStyles(t);
  return (
    <View style={f.slot} pointerEvents="box-none">
      <Pressable
        testID="tab-scan-pay"
        accessibilityLabel="Scan and Pay"
        hitSlop={10}
        onPress={() => router.push('/scan-to-pay')}
        style={({ pressed }) => [f.btn, pressed && { transform: [{ scale: 0.93 }] }]}>
        <LinearGradient colors={[t.brand, t.brandEnd]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={f.grad}>
          <Ionicons name="qr-code" size={26} color="#fff" />
        </LinearGradient>
      </Pressable>
      <Text style={f.label}>Scan & Pay</Text>
    </View>
  );
}

export default function TabLayout() {
  const insets = useSafeAreaInsets();
  const t = useThemeTokens();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: t.brand,
        tabBarInactiveTintColor: t.textMuted,
        tabBarAllowFontScaling: false,
        tabBarStyle: {
          backgroundColor: t.tabBarBg,
          borderTopColor: t.tabBarBorder,
          borderTopWidth: 1,
          height: 58 + insets.bottom,
          paddingBottom: insets.bottom > 0 ? insets.bottom : 8,
          paddingTop: 6,
        },
        tabBarItemStyle: {
          paddingHorizontal: 2,
        },
        tabBarLabelStyle: {
          fontSize: 11,
          fontWeight: '700',
          letterSpacing: 0,
        },
      }}
    >
      {/* Primary IA — Home · Shop · [Scan & Pay] · Play · Social */}
      <Tabs.Screen
        name="home"
        options={{
          title: 'Home',
          tabBarButtonTestID: 'tab-home',
          tabBarIcon: ({ color, size }) => <Ionicons name="home-outline" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="shop"
        options={{
          title: 'Shop',
          tabBarButtonTestID: 'tab-shop',
          tabBarIcon: ({ color, size }) => <Ionicons name="storefront-outline" size={size} color={color} />,
        }}
      />
      {/* Raised center FAB — opens the QR scanner → check-in / pay / earn */}
      <Tabs.Screen
        name="scan"
        options={{
          title: '',
          tabBarButton: () => <ScanPayFab />,
        }}
      />
      <Tabs.Screen
        name="games"
        options={{
          title: 'Play',
          tabBarButtonTestID: 'tab-play',
          tabBarIcon: ({ color, size }) => <Ionicons name="game-controller-outline" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="social"
        options={{
          title: 'Social',
          tabBarButtonTestID: 'tab-social',
          tabBarIcon: ({ color, size }) => <Ionicons name="people-outline" size={size} color={color} />,
        }}
      />
      {/* Hidden screens — still navigable, not in the tab bar. Listen is
          reached via the Home pillars; wallet via the Home points pill;
          profile/more via the Home drawer. */}
      <Tabs.Screen name="listen" options={{ href: null }} />
      <Tabs.Screen name="radio" options={{ href: null }} />
      <Tabs.Screen name="wallet" options={{ href: null }} />
      <Tabs.Screen name="profile" options={{ href: null }} />
      <Tabs.Screen name="podcasts" options={{ href: null }} />
      <Tabs.Screen name="trivia" options={{ href: null }} />
      <Tabs.Screen name="passport" options={{ href: null }} />
      <Tabs.Screen name="news" options={{ href: null }} />
    </Tabs>
  );
}

const fabStyles = (t: ThemeTokens) => StyleSheet.create({
  slot: { flex: 1, alignItems: 'center', justifyContent: 'flex-start' },
  btn: {
    width: 58, height: 58, borderRadius: 29, marginTop: -22,
    shadowColor: t.brand, shadowOpacity: 0.45, shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 }, elevation: 8,
    borderWidth: 4, borderColor: t.tabBarBg,
  },
  grad: { flex: 1, borderRadius: 29, alignItems: 'center', justifyContent: 'center' },
  label: { color: t.brand, fontSize: 11, fontWeight: '800', marginTop: 2 },
});
