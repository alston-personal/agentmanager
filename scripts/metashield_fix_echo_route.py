from pathlib import Path

p = Path('/home/ubuntu/metashield-protocol/web-feed/app/[wallet_address]/[platform]/page.tsx')
s = p.read_text(encoding='utf-8')

old = '''  const router = useRouter();
  const { locale } = useI18n();
  const ft = (key: Parameters<typeof feedTranslate>[1], variables?: Record<string, string | number>) => feedTranslate(locale, key, variables);
  const [walletAddress, setWalletAddress] = useState<string>("");
  const [resolvedIdentityKey, setResolvedIdentityKey] = useState<string>("");
  const [currentPlatform, setCurrentPlatform] = useState<string>("all");
'''
new = '''  const routeParams = React.use(params);
  const router = useRouter();
  const { locale } = useI18n();
  const ft = (key: Parameters<typeof feedTranslate>[1], variables?: Record<string, string | number>) => feedTranslate(locale, key, variables);
  const [walletAddress, setWalletAddress] = useState<string>(routeParams.wallet_address || "");
  const [resolvedIdentityKey, setResolvedIdentityKey] = useState<string>("");
  const [currentPlatform, setCurrentPlatform] = useState<string>((routeParams.platform || "all").toLowerCase());
'''
if old not in s:
    raise SystemExit('expected route-state initialization block not found')
s = s.replace(old, new, 1)

old_effect = '''  // Resolve dynamic route params and load persistent session
  useEffect(() => {
    params.then((p) => {
      setWalletAddress(p.wallet_address);
      setCurrentPlatform(p.platform.toLowerCase());
    });

    if (typeof window !== "undefined") {
'''
new_effect = '''  // Route params are unwrapped during render so SSR/hydration never emits empty /echo// links.
  // This effect only loads persistent browser session state.
  useEffect(() => {
    if (typeof window !== "undefined") {
'''
if old_effect not in s:
    raise SystemExit('expected async params effect not found')
s = s.replace(old_effect, new_effect, 1)

s = s.replace('studio.milkcat.org/reborn', 'studio.milkcat.org/echo')
p.write_text(s, encoding='utf-8')

print('echo_route_patch=PASS')
print('react_use_params=', 'const routeParams = React.use(params);' in s)
print('empty_initial_wallet=', 'useState<string>("")' in s[s.find('export default function PlatformFeed'):s.find('export default function PlatformFeed')+1200])
print('legacy_reborn_branding=', 'studio.milkcat.org/reborn' in s)
