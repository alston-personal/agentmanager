import importlib.util
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'social_runtime_local_config.py'
spec = importlib.util.spec_from_file_location('social_runtime_local_config', MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


class SocialRuntimeLocalConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.env = root / 'social-runtime.env'
        self.secret_dir = root / 'products'
        self.env.write_text(
            'AGENTOS_SOCIAL_PRODUCTS_JSON={}\n'
            'AGENTOS_SOCIAL_CONTROL_TOKEN=\n'
            'AGENTOS_THREADS_APP_ID=public-id\n'
            'AGENTOS_THREADS_APP_SECRET=provider-secret\n',
            encoding='utf-8',
        )
        os.chmod(self.env, 0o600)

    def tearDown(self):
        self.temp.cleanup()

    def test_control_token_generated_without_overwriting_other_secrets(self):
        before = self.env.read_text(encoding='utf-8')
        self.assertTrue(module.ensure_control_token(self.env))
        after = self.env.read_text(encoding='utf-8')
        self.assertIn('AGENTOS_THREADS_APP_SECRET=provider-secret', after)
        self.assertNotEqual(before, after)
        token = next(line.split('=', 1)[1] for line in after.splitlines() if line.startswith('AGENTOS_SOCIAL_CONTROL_TOKEN='))
        self.assertGreaterEqual(len(token), 40)
        self.assertFalse(module.ensure_control_token(self.env))
        self.assertEqual(after, self.env.read_text(encoding='utf-8'))
        self.assertEqual(stat.S_IMODE(self.env.stat().st_mode), 0o600)

    def test_register_product_is_idempotent_and_writes_fixed_secret_file(self):
        created, path = module.register_product(
            'leopardcat-tarot',
            'https://studio.milkcat.org/leopardcat-tarot',
            env_file=self.env,
            product_secret_dir=self.secret_dir,
        )
        self.assertTrue(created)
        self.assertEqual(path, self.secret_dir / 'leopardcat-tarot.env')
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        secret_text = path.read_text(encoding='utf-8')
        self.assertIn('AGENTOS_SOCIAL_PRODUCT_ID=leopardcat-tarot', secret_text)
        self.assertIn('AGENTOS_SOCIAL_RETURN_BASE=https://studio.milkcat.org/leopardcat-tarot', secret_text)
        key_line = next(line for line in secret_text.splitlines() if line.startswith('AGENTOS_SOCIAL_PRODUCT_KEY='))
        key = key_line.split('=', 1)[1]
        self.assertGreaterEqual(len(key), 40)

        raw = next(line.split('=', 1)[1] for line in self.env.read_text(encoding='utf-8').splitlines() if line.startswith('AGENTOS_SOCIAL_PRODUCTS_JSON='))
        registry = json.loads(raw)
        self.assertEqual(registry['leopardcat-tarot']['return_base'], 'https://studio.milkcat.org/leopardcat-tarot')
        self.assertEqual(registry['leopardcat-tarot']['api_key'], key)

        created_again, _ = module.register_product(
            'leopardcat-tarot',
            'https://studio.milkcat.org/leopardcat-tarot',
            env_file=self.env,
            product_secret_dir=self.secret_dir,
        )
        self.assertFalse(created_again)
        self.assertIn(key, path.read_text(encoding='utf-8'))

    def test_return_base_change_fails_closed_and_preserves_registration(self):
        module.register_product(
            'leopardcat-tarot',
            'https://studio.milkcat.org/leopardcat-tarot',
            env_file=self.env,
            product_secret_dir=self.secret_dir,
        )
        before = self.env.read_text(encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'social_product_registration_conflict'):
            module.register_product(
                'leopardcat-tarot',
                'https://example.invalid/other',
                env_file=self.env,
                product_secret_dir=self.secret_dir,
            )
        self.assertEqual(before, self.env.read_text(encoding='utf-8'))

    def test_invalid_product_or_return_base_rejected(self):
        for product_id in ('../escape', 'UPPER', 'a/b'):
            with self.assertRaises(ValueError):
                module.register_product(product_id, 'https://example.com/app', env_file=self.env, product_secret_dir=self.secret_dir)
        for return_base in ('http://example.com/app', 'https://user:pass@example.com/app', 'https://example.com/app?q=1'):
            with self.assertRaises(ValueError):
                module.register_product('safe-product', return_base, env_file=self.env, product_secret_dir=self.secret_dir)

    def test_status_is_secret_free(self):
        module.ensure_control_token(self.env)
        module.register_product(
            'leopardcat-tarot',
            'https://studio.milkcat.org/leopardcat-tarot',
            env_file=self.env,
            product_secret_dir=self.secret_dir,
        )
        value = module.status('leopardcat-tarot', env_file=self.env, product_secret_dir=self.secret_dir)
        self.assertEqual(
            value,
            {'registered': True, 'secret_file_present': True, 'control_token_configured': True},
        )
        self.assertNotIn('key', json.dumps(value).lower())
        self.assertNotIn('token', json.dumps(value).lower().replace('control_token_configured', ''))


if __name__ == '__main__':
    unittest.main()
