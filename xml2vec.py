# -*- coding: utf-8 -*-
"""Convert MusicXML and Series of Notes and Chords Bidirectionally

MusicXMLから曲情報と主旋律とコード進行を抽出
曲情報と旋律とコード進行からMusicXMLを生成

---変更予定の現行の仕様（2017/07/11）---
主旋律を一番上のパートとしている
    --> 指定できるように
テンション・ノートのタイプaddにしか対応していない
    --> alter, subにも対応する
抽出した結果はNote，Chordクラスのリスト，辞書である
    --> Numpy配列などに変換できるようにする
"""

from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET # 最初からこれ一つに統一すればよかった…
import datetime
import sys

#曲情報クラス
class PieceInfo:
    """Piece Information
    
    Key, Tempo, Time, total number of measures, divisions

    instance variables:
    measure_num -- 合計小節数[int]
    tempo       -- 曲のテンポ
                   {小節番号:[bpm[int], beat-unit[str], bpm(再生用)[int]], ...}
    key         -- 曲の調 
                   {Part-ID:{小節番号:値[int], ...}, ...}
    time        -- 曲の拍子
                   {小節番号:[拍子の分子, 拍子の分母], ...}
    divisions   -- この値を4分音符の長さとする
                   {Part-ID:値[int], ...}
    """
    
    # デフォルト値
    BPM       = 120       # beat per minute
    B_UNIT    = "quarter" # テンポを示す音符の単位 beat-unit
    S_TEMPO   = 120       # プレイバック時に用いられるBPM値 Sは<sound>のS
    DIVISIONS = 4         # 4分音符の長さをこの値とする(8分音符は半分の値，2分音符は2倍の値)
    FIFTHS    = 0         # 調
    BEATS     = 4         # 拍子の分子
    BEAT_TYPE = 4         # 拍子の分母
    PART_NUM  = 1         # パート数 # 現在は1しか扱わない
    
    # コンストラクタ
    def __init__(self):
        self.measure_num = 1
        self.part_num    = 1
        self.tempo       = {1:[PieceInfo.BPM, PieceInfo.B_UNIT, PieceInfo.S_TEMPO]} # {小節番号:[表記のテンポ, 表記に用いる音符, 再生時のBPM], ...}
        self.key         = {1:{1:PieceInfo.FIFTHS}} # {パートID:{小節番号:値, ...}, ...}
        self.time        = {1:[PieceInfo.BEATS, PieceInfo.BEAT_TYPE]} # {小節番号:[拍子の分子, 拍子の分母], ...}
        self.divisions   = {1:PieceInfo.DIVISIONS} # {パートID:値, ...}
        
    # 調の設定
    # part:パートid[int], measure:小節番号[int], fifth:調を表す値[int]
    # fifthに関してはREADME参照
    def set_key(self, part, measure, fifth):
        self.key[part][measure] = fifth

    # テンポの設定
    # measure[int], value[int]
    def set_tempo(self, measure, bpm, b_unit, s_tempo):
        self.tempo[measure] = [bpm, b_unit, s_tempo]

    # 拍子の設定
    # measure[int], beats[int], beat_type[int]
    def set_time(self, measure, beats, beat_type):
        self.time[measure] = [beats, beat_type]

    # divisionsの設定
    # part[int], value[int]
    def set_divisions(self, part, value):
        self.divisions[part] = value

# 音符クラス
class Note:
    """ Musical Note Description

    1個の音符の情報を格納するクラス
    インスタンス変数:
    step     : 階名[str]
    alter    : 変化記号[int]
    octave   : 音域[int]
    duration : 長さ[int]
    time     : 時刻[int]
    time_mod : 連符の一つであるかどうか
    """

    # 階名+オクターブ表記をMIDI規格のnote numberになおすためのdictionary
    step2num = {"C":0, "D":2, "E":4, "F":5, "G":7, "A":9, "B":11}

    # コンストラクタ
    # st[str], alt[int], octv[int], t[int], dur[int], mod[bool]
    def __init__(self, st, alt, octv, dur, t, mod=False):
        self.step     = st   # 階名
        self.alter    = alt  # 変化記号
        self.octave   = octv # 音域
        self.time     = t    # 時刻
        self.duration = dur  # 長さ
        self.time_mod = mod  # Time Modification(連符)の一つであるかどうか

    # 個の音をMIDI規格のnote numberに変換した値を返す
    # yamaha=Trueとするとyamaha式で計算する
    def get_midi_num(self, yamaha=False):
        # 基本は国際式
        if not yamaha:
            return 12 * (self.octave + 1) + step2num[self.step] + self.alter
        # yamaha=1ならyamaha式
        else:
            return 12 * (self.octave + 2) + step2num[self.step] + self.alter

    # durationと引数divisionsから音符の見た目の種類を返す
    # 64分音符から2倍全音符まで対応
    # 連符は2拍3連と1拍3連のみ対応 それ以外はエラーを返す
    def get_note_type(self, divisions):

        # 3連符
        if self.time_mod:# time modificationがあれば
            rate = float(divisions) / self.duration
            # 2拍3連
            if rate == 1.5:
                return "quarter"
            # 1拍3連
            elif rate == 3.0:
                return "eighth"
            # それ以外
            else:
                print "Error! Cannot use tuplet except quarter-note triplet and eigths-note triplet"
                quit() # 終了

        # 普通の音符の時
        rate = float(self.duration) / divisions
        if rate >= 0.0625 and rate < 0.125: # 長さが64分音符以上32分音符未満
            return "64th"
        elif rate >= 0.125 and rate < 0.25: # 32分音符以上16分音符未満
            return "32nd"
        elif rate >= 0.25 and rate < 0.5:   # 16分音符以上8分音符未満
            return "16th"
        elif rate >= 0.5 and rate < 1.0:    # 8分音符以上4分音符未満
            return "eighth"
        elif rate >= 1.0 and rate < 2.0:    # 4分音符以上2分音符未満
            return "quarter"
        elif rate >= 2.0 and rate < 4.0:    # 2分音符以上全音符未満
            return "half"
        elif rate >= 4.0 and rate < 8.0:    # 全音符以上倍全音符未満
            return "whole"
        elif rate >= 4.0 and rate < 16.0:   # 倍全音符以上
            return "breve"
        else:
            print "Error! Cannnot process the notes whose duration are %d on divisions=%d" % self.duration, divisions
            quit()
        
            
#コードクラス
class Chord:
    """Chord Description

    1個のコードの情報を格納するクラス
    instance variables:
    rt_* -- 根音のパラメータ
    dr_* -- テンションノートのパラメータ
    bs_* -- ベース音のパラメータ
    *_step  -- 階名 [str] dr_stepのみ[int]
    *_alt   -- 変化記号
    dr_type -- テンションの種類 (add, alter, subtract)
    ch_kind -- コードの種類
    ch_text -- 種類のテキスト表記    
    """

    #臨時記号とxx_alt変数の対応を示した辞書
    #とりあえずダブルシャープとダブルフラットまで対応
    accidental = {-2:u"♭♭", -1:u"♭", 0:u"", 1:u"♯", 2:u"♯♯"}
    
            
    # テンション・ノート設定
    # step:度数[int], alt:臨時記号[int]
    # dtype:テンションの種類(add, alter, subtract)
    def set_degree(self, step, alt, dtype):
        
        self.dr_step = step #テンションは度数表記なのでstepも整数
        self.dr_alt = alt
        self.dr_type = dtype

    # 分数コードのベース音設定
    # step:階名[char], alt:臨時記号[int]
    def set_bass(self, step, alt):
        
        self.bs_step = step
        self.bs_alt= alt
    
    # コンストラクタ
    # step:階名[char], alt:臨時記号[int]
    # kind:和音の種類[string], text:表記[string]
    def __init__(self, step, alt, kind, text):
        #基本要素
        self.rt_step = step
        self.rt_alt  = alt
        self.ch_kind = kind
        self.ch_text = text 
        #テンションノート
        self.set_degree(0, 0, "")
        #ベース
        self.set_bass("", 0) 

    # コード表記の文字列を返す
    # Return value: コードの文字列表現[string]
    def get_symbol(self):
        symbol = self.rt_step + Chord.accidental[self.rt_alt] + self.ch_text

        if self.dr_step:#テンション・ノートがあれば
            symbol = symbol + "(" + Chord.accidental[self.dr_alt] + str(self.dr_step) + ")"
            #とりあえずaddのときだけ考えておく．本来はdr_typeによってわけないとだめ 2017/05/30

        if self.bs_step:#分数コードであれば(コードオンコードは未対応)
            symbol = symbol + "/" + self.bs_step + Chord.accidental[self.bs_alt]

        return symbol


# MusicXMLからメロディとコードを抽出
def extract_music(soup):
    """Extract Melody and Chords data from MusicXML file

    MusicXMLを読み込んだsoupを入力し，そこから曲情報とメロディとコードを抽出してきます
    重音の場合は一番上のみ抽出します
    return (曲情報[PieceInfo, メロディ[Noteのリスト], コード{時刻:Chordなる辞書}])
    """

    melody = []      # 旋律 [Noteのインスタンス, ...]
    chords = {}      # コード進行 {時刻:コードのインスタンス, ....}
    cur_time = 0     # 現在の時刻
    tmp_duration = 0 # 音符の長さ
    piece = PieceInfo() # 曲情報
    
    # パートごとに
    for p in soup.find_all("part"):

        # 楽譜の頭
        cur_time = 0

        # 楽譜の最上段のパート（主旋律であると想定）                        
        # 主旋律はこのパートっていう指定ができるようにしてもいいかもしれない
        if p["id"] == "P1": 

            # 小節ごとに
            for m in p.find_all("measure"):

                cur_num = int(m["number"]) # 現在の小節番号
                
                # 属性，テンポ，コード，音符，巻き戻し
                for content in m.find_all({"attributes", "direction", "harmony", "note", "backup"}):

                    # 巻き戻し
                    if content.name == "backup":
                        cur_time -= int(content.duration.string)
                              
                    # 属性
                    if content.name == "attributes":
                        if content.find("key"): # 調
                            piece.set_key(1, cur_num, int(content.key.fifths.string))
                        if content.find("divisions"): # divisions
                            piece.set_divisions(1, int(content.divisions.string)) 
                        if content.find("time"): # 拍子
                            piece.set_time(cur_num, int(content.time.beats.string),
                                           int(content.time.find("beat-type").string))

                    # テンポ (directionのうちmetronome, soundのみ対象)
                    if content.name == "direction":
                        flg = 0
                        if content.find("sound"):
                            if "tempo" in content.sound:
                                s_tempo = int(content.sound["tempo"])
                                bpm     = s_tempo   # もしmetronomeがなかったらsound["tempo"]
                                b_unit  = "quarter" # から表記の値を決める
                                flg = 1
                                
                        if content.find("direction-type").find("metronome"):
                            tmp = content.find("direction-type").metronome
                            bpm     = int(tmp.find("per-minute").string)
                            b_unit  = tmp.find("beat-unit").string
                            if not flg: # もしsoundがなかったら
                                s_tempo = bpm
                        # セット
                        piece.set_tempo(cur_num, bpm, b_unit, s_tempo)
                            
                        
                    # コード
                    if content.name == "harmony":
                        # 根音
                        rt_step = content.root.find("root-step").string
                        if content.root.find("root-alter"):
                            rt_alt = int(content.root.find("root-alter").string)
                        else:
                            rt_alt = 0
                             
                        # 種類
                        h_kind = content.kind.string
                        h_text = content.kind["text"]

                        # 基本要素でコードインスタンス生成
                        chords[cur_time] = Chord(rt_step, rt_alt, h_kind, h_text)
                            
                        # テンション
                        if content.degree:
                            dr_step = int(content.degree.find("degree-value").string)
                            dr_alt  = int(content.degree.find("degree-alter").string)
                            dr_type = content.degree.find("degree-type").string
                            chords[cur_time].set_degree(dr_step, dr_alt, dr_type)
                            
                        # 分数コードのベース音
                        if content.bass:
                            bs_step = content.bass.find("bass-step").string
                            if content.bass.find("bass-alter"):
                                bs_alt = int(content.bass.find("bass-alter").string)
                            else:
                                bs_alt = 0

                            chords[cur_time].set_bass(bs_step, bs_alt)

                    # 音符 (重なっている音は一番下以外無視，durationを持たない音符は無視)
                    if content.name == "note" and not content.chord and content.duration:
                        # 長さ
                        note_dur = int(content.duration.string)
                        
                        # 音程のある音符
                        if content.pitch:
                            note_step = content.pitch.step.string
                            note_oct  = int(content.pitch.octave.string)
                            if content.pitch.alter:
                                note_alt = int(content.pitch.alter.string)
                            else:
                                note_alt = 0

                        # 休符
                        if content.rest:
                            note_step = "R" # 休符の階名はRとする
                            note_oct  = 0
                            note_alt  = 0
                            
                        # 連符かどうか
                        if content.find("time-modification"):
                            note_mod = True
                        else:
                            note_mod = False
                            
                        # 音符情報をリストに追加
                        melody.append(Note(note_step, note_alt, note_oct, note_dur, cur_time, note_mod))
                        
                        #現在時刻を音符の長さ分だけ進める
                        cur_time += note_dur

                    # 音符1個分の処理完了
                # 1 content分の処理完了
                
            # 1小節分の処理完了
            
            # 現在の小節数を曲情報インスタンスに格納しておく
            piece.measure_num = cur_num

        #それ以外のパート
        #コードのみ拾ってくる
        else:

             for m in p.find_all("measure"):
                
                for content in m.find_all({"harmony", "note", "backup"}):

                    #巻き戻し
                    if content.name == "backup":
                        cur_time -= int(content.duration.string)
                    
                    #コード
                    if content.name == "harmony":
                        #根音
                        rt_step = content.root.find("root-step").string
                        if content.root.find("root-alter"):
                            rt_alt = int(content.root.find("root-alter").string)
                        else:
                            rt_alt = 0
                            
                        #種類
                        h_kind = content.kind.string
                        h_text = content.kind["text"]

                        #基本要素でコードインスタンス生成
                        chords[cur_time] = Chord(rt_step, rt_alt, h_kind, h_text)
                            
                        #テンション
                        if content.degree:
                            dr_step = int(content.degree.find("degree-value").string)
                            dr_alt  = int(content.degree.find("degree-alter").string)
                            dr_type = content.degree.find("degree-type").string
                            chords[cur_time].set_degree(dr_step, dr_alt, dr_type)
                            
                        #分数コードのベース音
                        if content.bass:
                            bs_step = content.bass.find("bass-step").string
                            if content.bass.find("bass-alter"):
                                bs_alt = int(content.bass.find("bass-alter").string)
                            else:
                                bs_alt = 0

                            chords[cur_time].set_bass(bs_step, bs_alt)

                    #音符（現在時刻を取得するため）
                    if content.name == "note" and not content.chord and content.duration:
                        tmp_duration = int(content.duration.string)
                        cur_time += tmp_duration

                            
    return (piece, melody, chords)


# 既定のヘッダーを返すだけ
def WriteHeader():
    """Make MusicXML Header"""

    header = '<?xml version="1.0" encoding="UTF-8"?>\n' \
             + '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">'


    return header

# 既定の設定をtreeに書き込むだけ
# score:ElementTreeのElement
# あとで元の曲と同じ設定にするように改良予定
def WriteIdentification(score):

    identity = ET.SubElement(score, "identification")
    # 権利
    rights      = ET.SubElement(identity, "rights")
    rights.text = "----"
    # エンコード
    encoding      = ET.SubElement(identity, "encoding")
    software      = ET.SubElement(encoding, "software")
    software.text = "%s" % sys.argv[0]
    date          = ET.SubElement(encoding, "encoding-date")
    date.text     = str(datetime.date.today().strftime('%Y-%m-%d'))
    ## サポート
    sup1 = ET.SubElement(encoding, "supports",
                         {"element":"accidental", "type":"yes"})
    sup2 = ET.SubElement(encoding, "supports",
                         {"element":"beam", "type":"yes"})
    sup3 = ET.SubElement(encoding, "supports",
                         {"element":"print", "attribute":"new-page", "type":"yes", "value":"yes"})
    sup4 = ET.SubElement(encoding, "supports",
                         {"element":"print", "attribute":"new-systme", "type":"yes", "value":"yes"})
    sup5 = ET.SubElement(encoding, "supports",
                         {"element":"stem", "type":"yes"})


# 楽譜のデフォルト設定
# 全てMuseScoreの設定に従う
# score:ElementTreeのElement
def WriteDefaults(score):

    # 設定値
    mill       = 7.05556
    tenths_val = 40
    p_height   = 1683.78
    p_width    = 1190.55
    l_margin   = 56.6929
    r_margin   = 56.6929
    t_margin   = 56.6929
    b_margin   = 113.386
    w_font_size = 10
    l_font_size = 11
    
    defaults = ET.SubElement(score, "defaults")

    # スケーリング
    scaling = ET.SubElement(defaults, "scaling")
    millimeters = ET.SubElement(scaling, "millimeters")
    millimeters.text = str(mill)
    tenths = ET.SubElement(scaling, "tenths")
    tenths.text = str(tenths_val)

    # ページレイアウト
    pagelayout = ET.SubElement(defaults, "page-layout")
    pageheight = ET.SubElement(pagelayout, "page-height")
    pageheight.text = str(p_height)
    pagewidth = ET.SubElement(pagelayout, "page-width")
    pagewidth.text = str(p_width)
    ## ページマージン
    even_p_margin = ET.SubElement(pagelayout, "page-margins", {"type":"even"})
    e_l_margin = ET.SubElement(even_p_margin, "left-margin")
    e_r_margin = ET.SubElement(even_p_margin, "right-margin")
    e_t_margin = ET.SubElement(even_p_margin, "top-margin")
    e_b_margin = ET.SubElement(even_p_margin, "bottom-margin")
    e_l_margin.text = str(l_margin)
    e_r_margin.text = str(r_margin)
    e_t_margin.text = str(t_margin)
    e_b_margin.text = str(b_margin)
    odd_p_margin = ET.SubElement(pagelayout, "page-margins", {"type":"odd"})
    o_l_margin = ET.SubElement(odd_p_margin, "left-margin")
    o_r_margin = ET.SubElement(odd_p_margin, "right-margin")
    o_t_margin = ET.SubElement(odd_p_margin, "top-margin")
    o_b_margin = ET.SubElement(odd_p_margin, "bottom-margin")
    o_l_margin.text = str(l_margin)
    o_r_margin.text = str(r_margin)
    o_t_margin.text = str(t_margin)
    o_b_margin.text = str(b_margin)

    # フォント
    w_font = ET.SubElement(defaults, "word-font",
                           {"font-family":"FreeSerif", "font-size":str(w_font_size)})
    l_font = ET.SubElement(defaults, "lyric-font",
                           {"font-family":"FreeSerif", "font-size":str(l_font_size)})

# part list を作る
# 現在は楽器をピアノとして既定の内容を出力するだけ
# score:ElementTreeのElement
def WritePartList(score):

    part_list = ET.SubElement(score, "part-list")

    # 定数など INST, INST_abb, MIDI_Pは楽器依存
    ID_NUM    = 1 
    INST_NUM  = 1 
    INST      = u"ピアノ" # 楽器名
    INST_abb  = "Pno."   # 略称
    MIDI_port = 1 # midiポート
    MIDI_C    = 1 # midiのチャンネル
    MIDI_P    = 1 # ピアノのmidiでのprogram番号は1
    VOLUME    = 78.7402 # MuseScoreのデフォルト
    PAN       = 0       # 同上
    
    # パート
    part = ET.SubElement(part_list, "score-part",{"id":"P"+str(ID_NUM)})
    p_name = ET.SubElement(part, "part-name")
    p_name.text = INST
    p_abb  = ET.SubElement(part, "part-abbreviation")
    p_abb.text = INST_abb
    # score-instrument
    s_inst = ET.SubElement(part, "score-instrument",
                           {"id":"P{0}-I{1}".format(ID_NUM, INST_NUM)})
    i_name = ET.SubElement(s_inst, "instrument-name")
    i_name.text = INST
    # midi-instrument
    midi_d = ET.SubElement(part, "midi-device",
                           {"id":"P{0}-I{1}".format(ID_NUM, INST_NUM),
                            "port":str(MIDI_port)})
    midi_i = ET.SubElement(part, "midi-instrument",
                           {"id":"P{0}-I{1}".format(ID_NUM, INST_NUM)})
    midi_c = ET.SubElement(midi_i, "midi-channel")
    midi_c.text = str(MIDI_C)
    midi_p = ET.SubElement(midi_i, "midi-program")
    midi_p.text = str(MIDI_P)
    vol    = ET.SubElement(midi_i, "volume")
    vol.text    = str(VOLUME)
    pan    = ET.SubElement(midi_i, "pan")
    pan.text    = str(PAN)


# 小節に音符を書き込む
# measure[xml.etree.ElementTree.SubElement], note_info[Note], divisions[int]
def WriteNote(measure, note_info, divisions):

    # <note>タグ生成
    note = ET.SubElement(measure, "note")

    # 休符なら <rest>
    if note_info.step == "R":
        rest = ET.SubElement(note, "rest")

    else: # 音程の有る音符 <pitch>
        pitch = ET.SubElement(note, "pitch")
        step  = ET.SubElement(pitch, "step")
        step.text = note_info.step
        octave = ET.SubElement(pitch, "octave")
        octave.text = str(note_info.octave)
        if note_info.alter != 0:
            alter = ET.SubElement(pitch, "alter")
            alter.text = str(note_info.alter)

    # 長さ <duration>
    duration = ET.SubElement(note, "duration")
    duration.text = str(note_info.duration)

    # 声部 (1のみ) <voice>
    voice = ET.SubElement(note, "voice")
    voice.text = "1"

    # 表記上のタイプ <type>
    n_type = ET.SubElement(note, "type")
    n_type.text = note_info.get_note_type(divisions)

    # 連符であれば <time-modification>
    # 2拍3連と1拍3連のみなので既定の値を出力
    if note_info.time_mod:
        t_mod = ET.SubElement(note, "time-modification")
        act_n = ET.SubElement(t_mod, "actual-notes")
        act_n.text = "3"
        nrm_n = ET.SubElement(t_mod, "normal-notes")
        nrm_n.text = "2"

# 小節にコードを書き込む
# measure[xml.etree.ElementTree.SubElement], chord[Chord]
def WriteChord(measure, chord):

    # <harmony>タグ生成
    harmony = ET.SubElement(measure, "harmony", {"print-frame":"no"})

    # 根音の情報 <root>
    root = ET.SubElement(harmony, "root")
    rt_step = ET.SubElement(root, "root-step")
    rt_step.text = chord.rt_step
    if chord.rt_alt: # 変化記号があれば
        rt_alt = ET.SubElement(root, "root-alter")
        rt_alt.text = str(chord.rt_alt)

    # テンションノートがある場合
    if chord.dr_step:
        # コードの種類 <kind>
        kind = ET.SubElement(harmony, "kind",
                             {"text":chord.ch_text, "parentheses-degrees":"yes"})
        kind.text = chord.ch_kind

        # テンションノートの情報 <degree>
        degree = ET.SubElement(harmony, "degree")
        dr_val  = ET.SubElement(degree, "degree-value")
        dr_alt  = ET.SubElement(degree, "degree-alter") # degreeのaktはなぜか0でも記述される
        dr_type = ET.SubElement(degree, "degree-type")
        dr_val.text  = str(chord.dr_step)
        dr_alt.text  = str(chord.dr_alt)
        dr_type.text = chord.dr_type

    # テンションノートがない場合
    else:
        # コードの種類 <kind>
        kind = ET.SubElement(harmony, "kind", {"text":chord.ch_text})
        kind.text = chord.ch_kind


    # 分数コードの場合
    if chord.bs_step:
        # ベース音の情報 <bass>
        bass = ET.SubElement(harmony, "bass")
        bs_step = ET.SubElement(bass, "bass-step")
        # 変化記号があれば
        if chord.bs_alt:
            bs_alt = ET.SubElement(bass, "bass-alter")
            bs_alt.text = str(chord.bs_alt)
        
        
# 5線譜上の情報を書き込んでいく
# 入力はTreeElement, 楽譜情報, メロディ，コード
def WriteScore(score, piece_info, melody, chords):
    """楽譜情報をElementTreeに書き込む
    
    Keyword arguments:
    score      -- XMLを構成するTreeの頂点 [xml.etree.ElementTree.Element]
    piece_info -- 曲情報 [PieceInfo]
    melody     -- 旋律 [list]
    chords     -- コード進行 [dictionary of Chord]
    """
    
    # パートごと (現在は1パートのみ) 
    for p in range(1, piece_info.part_num + 1):

        # <part>タグ生成
        part = ET.SubElement(score, "part", {"id":"P%d" % p})
        
        # 現在時刻 (時刻の単位は4分音符の長さをdivisionsの値とした整数)
        cur_time = 0
        # 小節の開始時刻
        next_m_time = 0
        # 音符のインデックス
        i = 0
        
        # 小節ごと
        for m in range(1, piece_info.measure_num + 1):

            # m小節目を生成 <measure>
            measure = ET.SubElement(part, "measure", {"number":str(m)})

            # 調の変更，拍子，の変更があるか1小節目なら
            if m in piece_info.key[p] or m in piece_info.time or m == 1:
                # <attributes>タグを生成
                attributes = ET.SubElement(measure, "attributes")
                
                # <divisions>の設定 (1小節目のみ)
                if m == 1:
                    tmp_div = piece_info.divisions[p]
                    divisions = ET.SubElement(attributes, "divisions")
                    divisions.text = str(tmp_div)
                    
                    
                # 調の変更 <key>
                if m in piece_info.key[p]:
                    key = ET.SubElement(attributes, "key")
                    fifths = ET.SubElement(key, "fifths")
                    fifths.text = str(piece_info.key[p][m])

                # 拍子の変更 <time>
                if m in piece_info.time:
                    tmp_beats = piece_info.time[m][0]
                    tmp_btype = piece_info.time[m][1]
                    time = ET.SubElement(attributes, "time")
                    beats = ET.SubElement(time, "beats")
                    beat_type = ET.SubElement(time, "beat-type")
                    beats.text = str(tmp_beats)
                    beat_type.text = str(tmp_btype)

            # テンポの指定，変更があれば
            if m in piece_info.tempo:
                # タグを生成
                direction = ET.SubElement(measure, "direction", {"placement":"above"}) # 表示位置はaboveで固定
                dir_type  = ET.SubElement(direction, "direction-type")

                # metronome (楽譜に表記するテンポ)
                metronome = ET.SubElement(dir_type, "metronome", {"parentheses":"no"})
                b_unit    = ET.SubElement(metronome, "beat-unit")
                per_min   = ET.SubElement(metronome, "per-minute")
                b_unit.text  = piece_info.tempo[m][1]
                per_min.text = str(piece_info.tempo[m][0])

                # sound (再生用のテンポ)
                sound = ET.SubElement(direction, "sound", {"tempo":str(piece_info.tempo[m][2])})
                

            # 次の小節の開始時刻
            # この小節の長さ = 4分音符の長さ * (4 / 拍子の分母) * 拍子の分子
            next_m_time += int (tmp_div * (4.0 / tmp_btype) * tmp_beats)

            # 次の小節の開始時刻まで
            while cur_time < next_m_time:

                # コード
                # 現在時刻から始まるコードがあれば
                if cur_time in chords:
                    # コードの情報を書き込む
                    WriteChord(measure, chords[cur_time])

                # 音符
                # melodyのi番目の音符がこの時刻から始まる音符なら(必ずそうなるはず)
                if cur_time ==  melody[i].time:
                    # 音符の情報を書き込む
                    WriteNote(measure, melody[i], tmp_div)

                    # デバッグ用
                    #print "measure: %d" % m
                    #print "cur_time:%d, melody[%d].time:%d" % (cur_time, i, melody[i].time)
                    
                    # 現在時刻を音符の長さ分進める
                    cur_time += melody[i].duration
                    
                    # インデックスをインクリメント
                    i += 1

                # もし違かったら
                else:
                    # エラーを返す
                    print "Error! Note time Error"
                    print "cur_time:%d, melody[%d].time:%d" % (cur_time, i, melody[i].time)                 
                    quit()
            # while ここまで

        # 1小節分の処理完了
    # 1パートの処理完了
                
