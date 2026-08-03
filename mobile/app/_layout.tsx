import { View, ActivityIndicator } from 'react-native';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { AuthProvider, useAuth } from '../src/contexts/AuthContext';
import ChannelGateModal from '../src/components/ChannelGateModal';
import MiniPlayer from '../src/components/MiniPlayer';
import { configureAudioMode } from '../src/services/audioInit';
import { setupNativePlayer } from '../src/services/nativePlayerBridge';
import { COLORS } from '../src/constants/theme';

export default function RootLayout() {
  return (
    <AuthProvider>
      <StatusBar style="dark" />
      <AuthGatedStack />
      <ChannelGateModal />
    </AuthProvider>
  );
}

function AuthGatedStack() {
  const { loading } = useAuth();

  const initDone = require('react').useRef(false);
  if (!initDone.current) {
    initDone.current = true;
    configureAudioMode().then(() => setupNativePlayer()).catch(() => {});
  }

  if (loading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: COLORS.bg }}
        testID="auth-splash">
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  return (
    <View style={{ flex: 1 }}>
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: COLORS.bg } }}>
        <Stack.Screen name="index" />
        <Stack.Screen name="login" />
        <Stack.Screen name="forgot-password" />
        <Stack.Screen name="onboarding" />
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="now-playing" options={{ presentation: 'modal' }} />
        <Stack.Screen name="channels" options={{ presentation: 'modal' }} />
        <Stack.Screen name="lobbies" />
        <Stack.Screen name="lobby/[id]" options={{ presentation: 'modal' }} />
        <Stack.Screen name="play-and-win" />
        <Stack.Screen name="games/spin" options={{ presentation: 'modal' }} />
        <Stack.Screen name="games/trivia-game" options={{ presentation: 'modal' }} />
        <Stack.Screen name="games/lyric-game" options={{ presentation: 'modal' }} />
        <Stack.Screen name="games/predict" />
        <Stack.Screen name="games/campaign/[campaignId]" options={{ presentation: 'modal' }} />
        <Stack.Screen name="game/[campaignId]" options={{ presentation: 'modal' }} />
        <Stack.Screen name="commute" />
        <Stack.Screen name="leaderboard" />
        <Stack.Screen name="notifications" />
        <Stack.Screen name="coupons" />
        <Stack.Screen name="offer/[id]" options={{ presentation: 'modal' }} />
        <Stack.Screen name="coupon/[id]" options={{ presentation: 'modal' }} />
        <Stack.Screen name="scan-to-pay" options={{ presentation: 'modal' }} />
        <Stack.Screen name="pay-checkout/[token]" />
        <Stack.Screen name="my-splits" />
        <Stack.Screen name="billing" />
        <Stack.Screen name="trivia/play" />
        <Stack.Screen name="trivia/join" />
        <Stack.Screen name="trivia/rooms/create" />
        <Stack.Screen name="trivia/rooms/[code]" />
        <Stack.Screen name="passport/public/[userId]" options={{ presentation: 'modal' }} />
        <Stack.Screen name="podcast/channel/[id]" />
        <Stack.Screen name="podcast/episode/[id]" />
        <Stack.Screen name="podcast/highlights" />
        <Stack.Screen name="podcast/subscriptions" />
        <Stack.Screen name="advertiser/index" />
        <Stack.Screen name="advertiser/onboard" />
        <Stack.Screen name="advertiser/ai-create" />
        <Stack.Screen name="advertiser/campaign/new" />
        <Stack.Screen name="advertiser/campaign/[id]" />
        <Stack.Screen name="creator/index" />
        <Stack.Screen name="creator/channel/[id]" />
        <Stack.Screen name="creator/channel-settings/[id]" />
        <Stack.Screen name="creator/episode/[id]" />
        <Stack.Screen name="creator/magic-clips/[episodeId]" />
        <Stack.Screen name="creator/funnel" />
      </Stack>
      <MiniPlayer />
    </View>
  );
}
