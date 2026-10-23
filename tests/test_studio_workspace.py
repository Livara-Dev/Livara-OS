"""Real Studio workspace persistence, portable notes, and new local utilities."""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

from livara import studio


class WorkspaceStateTests(unittest.TestCase):
    def test_private_preferences_favorites_and_reset_persist(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = studio.WorkspaceState(Path(temporary) / 'studio')
            original = store.read()
            self.assertFalse(store.path.exists())
            original['favorites'].clear()
            self.assertEqual(store.read()['favorites'], ['json', 'calculator', 'unicode'])
            store.set_favorite('json', True)
            self.assertEqual(store.read()['favorites'][0], 'json')
            store.set_favorite('json', False)
            store.set_favorite('hex', True)
            store.set_preferences(accent='mint', density='compact', editor_size=18)
            reopened = studio.WorkspaceState(store.root)
            self.assertEqual(reopened.read()['preferences'], {'accent': 'mint', 'density': 'compact', 'editor-size': 18})
            self.assertEqual(stat.S_IMODE(store.root.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(store.path.stat().st_mode), 0o600)
            reset = reopened.reset_preferences()
            self.assertEqual(reset['preferences'], studio.WorkspaceState.PREFERENCE_DEFAULTS)
            self.assertIn('hex', reset['favorites'])
            self.assertNotIn('json', reset['favorites'])

    def test_recent_activity_is_bounded_unique_metadata_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = studio.WorkspaceState(Path(temporary))
            identifiers = [tool['id'] for tool in studio.TOOLS][:12]
            for identifier in identifiers:
                store.record_tool(identifier)
            recent = store.read()['recent']
            self.assertEqual([entry['id'] for entry in recent], list(reversed(identifiers[-8:])))
            self.assertTrue(all(set(entry) == {'id', 'used_at'} for entry in recent))
            store.record_tool(identifiers[-4])
            updated = store.read()['recent']
            self.assertEqual(updated[0]['id'], identifiers[-4])
            self.assertEqual(len({entry['id'] for entry in updated}), 8)
            self.assertNotIn('input', store.path.read_text())
            self.assertNotIn('output', store.path.read_text())

    def test_invalid_updates_do_not_partially_change_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = studio.WorkspaceState(Path(temporary))
            store.set_favorite('digest', True)
            before = store.path.read_bytes()
            for values in ({'accent': 'url(attack)'}, {'density': 'huge'}, {'editor_size': True},
                           {'editor_size': 10}, {'editor_size': 23}, {'unknown': 'value'},
                           {'editor_size': 14, 'editor-size': 15}):
                with self.subTest(values=values), self.assertRaises(ValueError):
                    store.set_preferences(**values)
                self.assertEqual(store.path.read_bytes(), before)
            for identifier in ('../outside', 'missing-tool', None):
                with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                    store.record_tool(identifier)
            with self.assertRaises(ValueError):
                store.set_favorite('json', 1)
            self.assertEqual(store.path.read_bytes(), before)

    def test_malformed_state_is_preserved_instead_of_reset(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = studio.WorkspaceState(Path(temporary))
            malformed = [b'{broken', json.dumps({'schema': 99}).encode()]
            for raw in malformed:
                store.path.write_bytes(raw)
                with self.assertRaisesRegex(ValueError, 'preserved'):
                    store.set_favorite('json', True)
                self.assertEqual(store.path.read_bytes(), raw)
            state = store.defaults()
            state['recent'] = [{'id': 'json', 'used_at': '2026-02-30T12:00:00+00:00'}]
            store.path.write_text(json.dumps(state))
            with self.assertRaisesRegex(ValueError, 'timestamp'):
                store.read()

    def test_symlink_and_special_storage_are_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / 'outside'
            outside.write_text('keep this')
            store = studio.WorkspaceState(root / 'studio')
            store.path.symlink_to(outside)
            with self.assertRaises(ValueError):
                store.read()
            self.assertEqual(outside.read_text(), 'keep this')
            store.path.unlink()
            os.mkfifo(store.path)
            with self.assertRaisesRegex(ValueError, 'regular file'):
                store.read()
            link = root / 'linked-root'
            link.symlink_to(store.root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symbolic'):
                studio.WorkspaceState(link / 'nested')


class CatalogAndUtilityTests(unittest.TestCase):
    def test_search_combines_tokens_categories_and_favorites(self):
        self.assertEqual([tool['id'] for tool in studio.search_tools('json format')], ['json'])
        self.assertEqual(studio.search_tools('not a possible tool phrase'), [])
        selected = studio.search_tools('', 'Favorites', ['digest', 'json'])
        self.assertEqual({tool['id'] for tool in selected}, {'digest', 'json'})
        self.assertTrue(all(tool['category'] == 'Files' for tool in studio.search_tools('', 'Files')))
        self.assertIn('hex', [tool['id'] for tool in studio.search_tools('uTf-8 hex')])
        with self.assertRaises(ValueError):
            studio.search_tools('', 'not-a-category')
        with self.assertRaises(ValueError):
            studio.search_tools('x' * 257)

    def test_exact_utf8_digests_and_hex_roundtrip(self):
        value = 'لیوارا · café ✨\n'
        result = json.loads(studio.run_tool('digest', value, 'sha256'))
        self.assertEqual(result['hex'], hashlib.sha256(value.encode()).hexdigest())
        self.assertEqual(result['utf8_bytes'], len(value.encode()))
        for algorithm in ('sha512', 'blake2b'):
            self.assertEqual(json.loads(studio.run_tool('digest', value, algorithm))['hex'], hashlib.new(algorithm, value.encode()).hexdigest())
        encoded = studio.run_tool('hex', value, 'encode')
        self.assertEqual(studio.run_tool('hex', encoded, 'decode'), value)
        for value in ('0', 'gg', 'ff'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                studio.run_tool('hex', value, 'decode')
        with self.assertRaises(ValueError):
            studio.run_tool('digest', 'hello', 'md5')

    def test_case_and_naming_preserve_unicode_words(self):
        self.assertEqual(studio.run_tool('textcase', 'BuildSomething beautiful!', 'snake'), 'build_something_beautiful')
        self.assertEqual(studio.run_tool('textcase', 'لیوارا زیبا', 'kebab'), 'لیوارا-زیبا')
        self.assertEqual(studio.run_tool('textcase', 'Straße', 'casefold'), 'strasse')
        with self.assertRaises(ValueError):
            studio.run_tool('textcase', 'x', '__class__')

    def test_json_paths_read_data_without_expression_evaluation(self):
        original = {'project': {'name': 'Livara'}, 'items': [{'ready': True}], 'a/b': {'~key': 'yes'}, 'فارسی': 'زیبا'}
        value = json.dumps(original, ensure_ascii=False)
        for query, expected in [('project.name', 'Livara'), ('items[0].ready', True), ('/a~1b/~0key', 'yes'), ('/فارسی', 'زیبا'), ('$', original)]:
            with self.subTest(query=query):
                self.assertEqual(json.loads(studio.run_tool('jsonpath', value, query)), expected)
        for query in ('items[999]', 'items[-1]', 'project.name()', 'project..name', 'items.[0]', '/a~2b'):
            with self.subTest(query=query), self.assertRaises(ValueError):
                studio.run_tool('jsonpath', value, query)

    def test_markdown_outline_skips_fenced_fake_headings(self):
        value = '# Real heading\n\n```python\n# code comment\n```\n\n## Next\n[Livara](https://livara.org)\n'
        report = json.loads(studio.run_tool('markdown', value, 'outline'))
        self.assertEqual([heading['text'] for heading in report['headings']], ['Real heading', 'Next'])
        self.assertEqual(report['fenced_code_blocks'], 1)
        self.assertEqual(report['links'], [{'label': 'Livara', 'destination': 'https://livara.org'}])
        self.assertEqual(studio.run_tool('markdown', '# Hello\n**Welcome** [home](https://example.org)', 'plain'), 'Hello\nWelcome home')


class ArchivedNoteTests(unittest.TestCase):
    def test_archived_search_read_export_and_restore_preserve_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            notes = studio.NoteStore(Path(temporary) / 'notes')
            identifier = notes.save('A [private] idea', 'A Persian note: لیوارا\n')
            self.assertEqual(notes.list_archived(), [])
            notes.archive(identifier)
            archived = notes.read_archived(identifier)
            self.assertEqual(notes.list_notes(), [])
            self.assertEqual(notes.list_archived('PERSIAN')[0]['id'], identifier)
            self.assertIn('# A \\[private\\] idea\n', studio.note_export(archived))
            self.assertTrue(studio.note_export(archived, 'text').endswith('A Persian note: لیوارا\n'))
            notes.restore(identifier)
            self.assertEqual(notes.read(identifier)['body'], archived['body'])
            self.assertEqual(notes.list_archived(), [])
            with self.assertRaises(ValueError):
                studio.note_export(archived, 'html')

    def test_archive_directory_symlink_cannot_read_or_move_external_notes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            notes = studio.NoteStore(root / 'notes')
            external = root / 'external'
            external.mkdir()
            identifier = 'a' * 32
            file = external / (identifier + '.json')
            file.write_text(json.dumps({'schema': 1, 'id': identifier, 'title': 'Outside', 'body': 'untouched', 'updated_at': '2026-01-01'}))
            (notes.root / 'archive').symlink_to(external, target_is_directory=True)
            for action in (lambda: notes.list_archived(), lambda: notes.read_archived(identifier), lambda: notes.restore(identifier)):
                with self.assertRaisesRegex(ValueError, 'real directory'):
                    action()
            self.assertTrue(file.exists())


if __name__ == '__main__':
    unittest.main()
