import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useThemeTokens } from '../../src/theme/ThemeProvider';

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
      {/* Primary IA — Home · Listen · Shop · Play · Social */}
      <Tabs.Screen
        name="home"
        options={{
          title: 'Home',
          tabBarButtonTestID: 'tab-home',
          tabBarIcon: ({ color, size }) => <Ionicons name="home-outline" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="listen"
        options={{
          title: 'Listen',
          tabBarButtonTestID: 'tab-listen',
          tabBarIcon: ({ color, size }) => <Ionicons name="radio-outline" size={size} color={color} />,
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
      {/* Hidden screens — still navigable, not in the tab bar. Wallet is
          reached via the Home points pill; profile/more via the Home drawer. */}
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
