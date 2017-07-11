# -*- coding: utf-8 -*-
"""Read MusicXML with multi part and write MusicXML with only melody part

xml2vecとvec2xmlのテスト用
複数パートのMusicXMLを読んでそこから一番上のパートとコード進行を抽出，
そのパートとコード進行だけのMusicXMLを作成して保存する
"""

import sys
import time
import re
import xml2vec as x2v
import xml.etree.ElementTree as ET
from xml.dom import minidom
from bs4 import BeautifulSoup


# mainで作ったMusicXMLにヘッダを追加して，改行，インデントを施す
def finalize(score):
    """Return finalized MusicXML
    
    Adds Header of MusicXML, Breaks lines and Indents
    """
    rough_string = ET.tostring(score, 'utf-8')
    rough_string = x2v.WriteHeader() + rough_string
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")


if __name__ == "__main__":

    
    ###### 読み込み ######

    #引数の取得
    argvs = sys.argv
    argc = len(argvs)
    if (argc != 3):
        print "Usage: python %s input-name.xml output-name.xml" % argvs[0]
        quit()

    # MusicXMLを読み込む
    print "loading %s ..." % argvs[1]
    soup = BeautifulSoup(open(argvs[1], "r").read(), "lxml")

    # 曲情報，メロディ，コードの抽出
    print "extracting melody and chords from %s ..." % argvs[1]
    piece_info, melody, chords = x2v.extract_music(soup)

    
    ###### デバッグ用 ######

    #print "divisions: %d" % piece_info.divisions[1]

    #print chords


    #for ch_time in sorted(chords.keys()):
    #    print "(%d, %s)" % (ch_time, chords[ch_time].get_symbol())

    
    ###### MusicXML生成 ######

    # 根ノード 
    score = ET.Element("score-partwise")

    # 識別情報 (タイトル，作曲者など)
    print "writing identification"
    x2v.WriteIdentification(score)

    # 各種デフォルト設定
    print "writing defaults settings"
    x2v.WriteDefaults(score)

    # パートリスト
    print "writing part list"
    x2v.WritePartList(score)

    # 五線譜上の情報を書き込む
    print "writing melody and chords"
    x2v.WriteScore(score, piece_info, melody, chords)

    f = open(argvs[2], "w")
    f.write(finalize(score).encode('utf-8'))

    print "Process Completed"
    
