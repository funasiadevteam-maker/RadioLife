import { View, ActivityIndicator, Platform } from 'react-native';
import { useEffect } from 'react';
import { Stack, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import * as Notifications from 'expo-notifications';
import * as Linking from 'expo-linking';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { AuthProvider, useAuth } from '../src/contexts/AuthContext';
import ChannelGateModal from '../src/components/ChannelGateModal';
import MiniPlayer from '../src/components/MiniPlayer';
import { RewardProvider } from '../src/components/RewardOverlay';
import { registerForPush } from '../src/utils/pushNotifications';
import { configureAudioMode } from '../src/services/audioInit';
import { setupNativePlayer } from '../src/services/nativePlayerBridge';
import { COLORS } from '../src/constants/theme';

// Foreground display behaviour — MODULE SCOPE, before any component.
if (Platform.OS !== 'web') {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
      shouldShowBanner: true,
      shouldShowList: true,
    }),
  });
}

// Android default channel — MODULE SCOPE, before any push can arrive.
if (Platform.OS === 'android') {
  Notifications.setNotificationChannelAsync('default', {
    name: 'Default',
    importance: Notifications.AndroidImportance.MAX,
    sound: 'default',
  });
}

export default function RootLayout() {
  return (
    <AuthProvider>
      <RewardProvider>
        <StatusBar style="dark" />
        <AuthGatedStack />
        <ChannelGateModal />
      </RewardProvider>
    </AuthProvider>
  );
}

function AuthGatedStack() {
  const { loading, user } = useAuth();
  const router = useRouter();

  const initDone = require('react').useRef(false);
  if (!initDone.current) {
    initDone.current = true;
    configureAudioMode().then(() => setupNativePlayer()).catch(() => {});
  }

  // Register this device for push whenever a user is signed in (tokens rotate).
  useEffect(() => {
    if (user?.user_id) registerForPush(user.user_id);
  }, [user?.user_id]);

  // Notification tap handling + denied-permission weekly nudge.
  useEffect(() => {
    if (Platform.OS === 'web') return;

    const openFromData = (data: any) => {
      const url = data?.deeplink || data?.action_url;
      if (!url) return;
      url.startsWith('http') ? Linking.openURL(url) : router.push(url);
    };

    const tapSub = Notifications.addNotificationResponseReceivedListener((response) => {
      openFromData(response?.notification?.request?.content?.data || {});
    });

    Notifications.getLastNotificationResponseAsync().then((response) => {
      if (response) openFromData(response.notification.request.content.data || {});
    });

    (async () => {
      const { status, canAskAgain } = await Notifications.getPermissionsAsync();
      if (status !== 'denied' || canAskAgain) return;
      const lastNudge = await AsyncStorage.getItem('pushNudgeAt');
      const oneWeek = 7 * 24 * 60 * 60 * 1000;
      if (lastNudge && Date.now() - Number(lastNudge) <= oneWeek) return;
      await AsyncStorage.setItem('pushNudgeAt', String(Date.now()));
      Linking.openSettings();
    })();

    return () => { tapSub.remove(); };
  }, [router]);

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
        <Stack.Screen name="dining/index" />
        <Stack.Screen name="dining/play" />
        <Stack.Screen name="dining/pass" />
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
