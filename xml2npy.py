# -*- coding: utf-8 -*-
"""Convert MuiscXML into Numpy array with only one single melody part

MusicXMLを読み込んで，その第１パートのメロディをNumpy配列に変換して保存する
指定した小節数ごとに切り取り，それを1ファイルとして.npy形式で保存する
切り取る小節数はこのスクリプトでは4小節固定で，1つまでの全休符を許してカットする
4/4拍子の曲のみに対応

2017/10/16
"""

import sys
import re
import argparse
import os
import csv

import numpy as np

import xml2vec as x2v
from bs4 import BeautifulSoup


def extract_melody(xml_file):
    """Extract Melody from xml_file"""
    
    # MusicXMLを読み込む
    print "loading %s ..." % xml_file
    soup = BeautifulSoup(open(xml_file, "r").read(), "lxml")

    # 曲情報，メロディ，コードの抽出
    print "extracting melody and chords from %s ..." % xml_file
    piece_info, melody, _ = x2v.extract_music(soup)

    return piece_info, melody


def save_as_array(melody_arr, name, out_dir):
    """Save melody as an array

    args:
    melody_arr -- メロディ配列 [numpy.ndarray]
    name       -- 保存時のファイル名
    out_dir    -- 保存先パス
    """
    
    
    # 転置，上下反転でピアノロール風の配列として保存
    melody_arr = np.flipud(melody_arr.T)
    
    out_path  =  os.path.join(out_dir, name)
    np.save(out_path, melody_arr)

    print '{} is saved.'.format(out_path)
    
    
def convert_melody_into_array(melody, piece_info, name, out_dir,
                              r=24, pitch_extent=(36, 96), cut_num=4, rest_limit=1, yamaha=False):
    """Convert Melody into Numpy array

    args:
    melody       -- 音符列を格納したリスト
    piece_info   -- 曲情報 [PieceInfo]
    name         -- ファイル名
    out_dir      -- 保存先パス
    r            -- 正規化時の基準値 (4分音符の長さ) [int] (default=24)
    pitch_extent -- 使用する音域の下限と上限のMIDI Note number (default=(36, 96))
    cut_num      -- 切り取る単位 (小節数) [int] (default=24)
    rest_limit   -- 切り取る小節内で，全休符を許す小節数の上限 (default=1)
    yamaha       -- Trueに設定した場合，MIDI note numberをYAMAHA式で計算する"""
    
    measure_num = piece_info.measure_num
    length      = piece_info.length
    div         = piece_info.divisions[1]
    l_note      = pitch_extent[0]
    h_note      = pitch_extent[1] - 1
    cut_num     = cut_num
    rate = r / div                   

    cur_time  = 0
    beats     = 4
    btype     = 4
    next_time = 0
    
    index = sorted(piece_info.time.keys())

    for i in range(len(index)):
        
        # 最後の拍子変更
        if i == len(index) - 1:
            # 最後の小節までの長さ
            m_num = measure_num - index[i] + 1
        # それ以外
        else:
            # 次に拍子が変わるまでの小節数
            m_num = index[i+1] - index[i]

            # アウフタクトがあれば
        if index[i] == 0:
            cur_time += piece_info.upbeat_l            
            m_num -= 1
                        
        # 変更した拍子が続く小節数がcut_num以上かつ4/4拍子ならメロディを配列に変換
        save_list = True
        last_k = 0
        if m_num >= cut_num and piece_info.time[index[i]] == [4, 4]:

            beats, btype = piece_info.time[index[i]]            
            m_len = int(div * (4.0 / btype) * beats)    
            # 次に拍子が変わる時刻（曲の終了時刻）
            next_time = cur_time + m_num * m_len
            
            # cur_timeからはじまる音符を探す
            for j in range(last_k, len(melody)):
                if melody[j].time == cur_time:
                    k = j
                    break
            else:
                print "Error! The note which starts on time:{} does not exist.".format(cur_time)
                quit()

            count = 0 # 開始位置からの小節数
            while cur_time < next_time - m_len * (cut_num - 1):

                # メロディを格納する配列
                melody_arr = np.zeros((m_len * rate * cut_num, (h_note-l_note)+1), dtype=np.int8)
                
                # 4小節ごとに切り取る
                c = 0
                tmp_dur = 0
                h_rest_num = 0
                save_list = True
                while tmp_dur < m_len * cut_num:                                        
                   
                    # 休符でなければ
                    if melody[k].step != 'R':
                        # 所定の音域内にあるかチェック
                        assert h_note >= melody[k].get_midi_num() >= l_note, \
                            "The note is not in expected pitch extent."
                        # 現在の時刻の，音階に対応する要素を1とする
                        for j in range(melody[k].duration * rate):                                            
                            melody_arr[tmp_dur * rate + j][melody[k].get_midi_num() - l_note] = 1                
                            
                    # 休符の場合
                    else:
                        # 全休符の場合
                        if melody[k].duration == m_len:
                            # 全休符を数える
                            h_rest_num += 1 
                                                                                 
                    # インクリメント
                    tmp_dur += melody[k].duration
                    k += 1
                    c += 1
                    last_k = k
                    
                    # 2小節目の最初の音符のインデックスを記録しておく                
                    if tmp_dur == m_len:
                        # 次はこの位置から切り取る
                        next_k = k 
                        
                    # 全休符が設定値より多ければその区間は使わない
                    if h_rest_num > rest_limit:
                        save_list = False
                        break
                
                # メロディを保存
                if save_list:
                    # ファイル名: 元のファイル名_区間の開始小節-区間の終了小節.npy
                    file_name = name + '_' + str(index[i]+count) + '-' + str(index[i]+count+cut_num) + '.npy'
                    save_as_array(melody_arr, file_name, out_dir)
    
                # 開始位置を1小節進める
                k = next_k
                cur_time += m_len
                # 開始位置からの小節数をインクリメント
                count += 1

            # 現在時刻を次に拍子が変わる時刻へ 
            cur_time += m_len * (cut_num - 1)
                
        else:
            # 現在時刻を次に拍子が変わる時刻まで進める
            # 次に拍子が変わる時刻（または曲の終了時刻）
            beats, btype = piece_info.time[index[i]]
            next_time = cur_time + m_num * int(div * (4.0 / btype) * beats)
            cur_time = next_time        
    
                    
def get_pitch_extent(melody, yamaha=False):
    """Find highest and lowest note numbers from melody

    args:
        melody -- 音符列を格納したリスト
        yamaha -- Trueにした場合  Midi note number をYAMAHA式で計算する

    return: highest midi note number[int], lowest midi note number[int]"""

    highest = 0
    lowest   = 127
    
    for note in melody:

        if note.step == 'R':
            continue
        
        midi_num = note.get_midi_num(yamaha)
        
        if midi_num > highest:
            highest = midi_num
            
        if midi_num < lowest:
            lowest = midi_num
        
    return highest, lowest
            

def main():

    # 引数取得
    parser = argparse.ArgumentParser(description='Convert MusicXML into Numpy array')
    parser.add_argument('--in_file', '-i', default='',
                        help="""Input XML file. IN_FILE or IN_DIR must be specified
                        Output file name is NAME.npy""")
    parser.add_argument('--in_dir', '-d', default='',
                        help='Directory of MusicXML files')
    parser.add_argument('--out_dir', '-o', default='',
                        help='Directry of output files')
    parser.add_argument('--divisions', type=int, default=24,
                        help='Divisions used in length normalization (default=24)')    
    parser.add_argument('--output_info', default='',
                        help="""Output file with information of input musical pieces
                        File name is 'OUTPUT_INFO.csv', and it is saved in OUT_DIR
                        The info. contains following elements;
                        ['name', 'm_num', 'divisions', 'time', 'tempo', 'key', 'highest', 'lowest']""")
    parser.add_argument('--look', action="store_true", default=False,
                        help="Just looks over xmls and output information if this argument is set")

    args = parser.parse_args()

    # データ読み込み
    if args.in_dir != '':
        all_files = os.listdir(args.in_dir)
        xmls = [f for f in all_files if ('xml' in f)]
        root = args.in_dir 
    elif args.in_file != '':
        root, fname = os.path.split(args.in_file)
        xmls = [fname]
    else:
        print "Error! IN_FILE or IN_DIR must be specified"
        exit

    # 曲情報リスト
    infos = []

    # メロディを読み込んで配列に変換
    for xml in xmls:

        # 曲情報とメロディを抽出
        info, melody = extract_melody(os.path.join(root,  xml))

        # 曲情報を出力する場合
        if args.output_info != '':
            # 音域
            highest, lowest = get_pitch_extent(melody)
            # 曲情報リストに情報を追加
            infos.append({'name':xml, 'm_num':info.measure_num, 'divisions':info.divisions[1],
                          'time':info.time, 'tempo':info.tempo, 'key':info.key[1],
                          'highest':highest, 'lowest':lowest})

        # args.divisionsを割り切れるdivisionsを持つファイルのみ処理
        if args.divisions % info.divisions[1] == 0 and not args.look:
            name, _ = os.path.splitext(xml)
            convert_melody_into_array(melody, info, name, args.out_dir)
        
    # 曲情報の出力
    if args.output_info != '':

        print "Saving infomation of musical pieces into %s ..." % args.output_info

        # ヘッダ
        header = ['name', 'm_num', 'divisions', 'time',
                  'tempo', 'key', 'highest', 'lowest']

        # 書き込む
        with open(os.path.join(args.out_dir, args.output_info+'.csv'), 'w') as f:

            writer = csv.DictWriter(f, header)

            # ヘッダの書き込み
            header_row = {k:k for k in header}
            writer.writerow(header_row)

            for row in infos:
                writer.writerow(row)
            
        
if __name__ == "__main__":

    main()
    
