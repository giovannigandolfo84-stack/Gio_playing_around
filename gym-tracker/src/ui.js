import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { C } from './theme';

export const Title = ({ children, sub }) => (
  <View style={{ marginBottom: 16 }}>
    <Text style={s.title}>{children}</Text>
    {sub ? <Text style={s.muted}>{sub}</Text> : null}
  </View>
);

export const Card = ({ children, style }) => <View style={[s.card, style]}>{children}</View>;

export const Btn = ({ label, onPress, kind = 'primary', small, style, disabled }) => (
  <Pressable
    onPress={onPress}
    disabled={disabled}
    style={({ pressed }) => [
      s.btn,
      small && s.btnSmall,
      kind === 'primary' && { backgroundColor: C.accent },
      kind === 'ghost' && { backgroundColor: C.card2 },
      kind === 'danger' && { backgroundColor: 'transparent', borderWidth: 1, borderColor: C.danger },
      (pressed || disabled) && { opacity: 0.6 },
      style,
    ]}
  >
    <Text
      style={[
        s.btnText,
        small && { fontSize: 14 },
        { color: kind === 'primary' ? C.accentText : kind === 'danger' ? C.danger : C.text },
      ]}
    >
      {label}
    </Text>
  </Pressable>
);

export const Input = (props) => (
  <TextInput placeholderTextColor={C.muted} keyboardAppearance="dark" {...props} style={[s.input, props.style]} />
);

export const Muted = ({ children, style }) => <Text style={[s.muted, style]}>{children}</Text>;
export const T = ({ children, style }) => <Text style={[s.text, style]}>{children}</Text>;

export const s = StyleSheet.create({
  title: { color: C.text, fontSize: 30, fontWeight: '800', letterSpacing: -0.5 },
  text: { color: C.text, fontSize: 16 },
  muted: { color: C.muted, fontSize: 14 },
  card: {
    backgroundColor: C.card,
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.border,
  },
  btn: { borderRadius: 12, paddingVertical: 14, paddingHorizontal: 18, alignItems: 'center' },
  btnSmall: { paddingVertical: 8, paddingHorizontal: 12, borderRadius: 10 },
  btnText: { fontSize: 16, fontWeight: '700' },
  input: {
    backgroundColor: C.card2,
    color: C.text,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 16,
  },
  row: { flexDirection: 'row', alignItems: 'center' },
});
