import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { StoreProvider, useStore } from './src/store';
import { C } from './src/theme';
import TrainScreen from './src/screens/TrainScreen';
import WorkoutScreen from './src/screens/WorkoutScreen';
import ProgramScreen from './src/screens/ProgramScreen';
import HistoryScreen from './src/screens/HistoryScreen';
import ProgressScreen from './src/screens/ProgressScreen';

const TABS = [
  { key: 'train', label: 'Allena', icon: '🏋️' },
  { key: 'program', label: 'Programma', icon: '📋' },
  { key: 'history', label: 'Storico', icon: '🗓️' },
  { key: 'progress', label: 'Progressi', icon: '📈' },
];

function Root() {
  const { state, ready } = useStore();
  const [tab, setTab] = useState('train');

  if (!ready) {
    return (
      <View style={[st.fill, { justifyContent: 'center' }]}>
        <ActivityIndicator color={C.accent} />
      </View>
    );
  }

  // An active workout takes over the whole screen until finished or discarded.
  if (state.active) return <WorkoutScreen />;

  const Screen = { train: TrainScreen, program: ProgramScreen, history: HistoryScreen, progress: ProgressScreen }[tab];

  return (
    <View style={st.fill}>
      <View style={st.fill}>
        <Screen />
      </View>
      <SafeAreaView edges={['bottom']} style={st.tabbar}>
        {TABS.map((t) => (
          <Pressable key={t.key} onPress={() => setTab(t.key)} style={st.tab}>
            <Text style={{ fontSize: 20, opacity: tab === t.key ? 1 : 0.45 }}>{t.icon}</Text>
            <Text style={[st.tabLabel, tab === t.key && { color: C.accent }]}>{t.label}</Text>
          </Pressable>
        ))}
      </SafeAreaView>
    </View>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <StoreProvider>
        <StatusBar style="light" />
        <View style={st.fill}>
          <Root />
        </View>
      </StoreProvider>
    </SafeAreaProvider>
  );
}

const st = StyleSheet.create({
  fill: { flex: 1, backgroundColor: C.bg },
  tabbar: {
    flexDirection: 'row',
    backgroundColor: C.card,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.border,
  },
  tab: { flex: 1, alignItems: 'center', paddingTop: 8, paddingBottom: 4 },
  tabLabel: { color: C.muted, fontSize: 11, marginTop: 2, fontWeight: '600' },
});
