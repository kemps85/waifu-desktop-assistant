from waifu.reply import Do, Remember, Say, parse_stream

def test_two_lines_split_across_chunks():
    chunks = ['{"mood":"happy","ja":"やあ","vi":"Ch', 'ào"}\n{"remember":"Người dùng thích phở"}\n']
    assert list(parse_stream(chunks)) == [Say("happy", "やあ", "Chào"), Remember("Người dùng thích phở")]

def test_last_line_without_newline():
    assert list(parse_stream(['{"mood":"sad","ja":"a","vi":"b"}'])) == [Say("sad", "a", "b")]

def test_unknown_mood_becomes_normal():
    assert list(parse_stream(['{"mood":"angry","ja":"a","vi":"b"}\n'])) == [Say("normal", "a", "b")]

def test_plain_text_fallback():
    assert list(parse_stream(["Xin chào cậu\n"])) == [Say("normal", "", "Xin chào cậu")]

def test_skips_blank_and_fences():
    chunks = ["```json\n", "\n", '{"mood":"shy","ja":"a","vi":"b"}\n', "```\n"]
    assert list(parse_stream(chunks)) == [Say("shy", "a", "b")]

def test_object_without_known_keys_is_skipped():
    assert list(parse_stream(['{"foo":1}\n', '{"remember":"  "}\n'])) == []

def test_non_object_json_is_plain_text():
    assert list(parse_stream(["123\n"])) == [Say("normal", "", "123")]

def test_yields_before_stream_ends():
    def gen():
        yield '{"mood":"happy","ja":"a","vi":"b"}\n'
        raise RuntimeError("không được đọc tiếp trước khi yield dòng đầu")
    assert next(parse_stream(gen())) == Say("happy", "a", "b")

def test_do_line_parsed_and_normalized():
    chunks = ['{"do":" OPEN ","arg":" chrome "}\n', '{"do":"mute"}\n', '{"do":"  ","arg":"x"}\n']
    assert list(parse_stream(chunks)) == [Do("open", "chrome"), Do("mute", "")]
