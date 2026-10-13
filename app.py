import os
import tempfile
import streamlit as st
from google import genai
from google.genai.errors import ClientError
from streamlit_mic_recorder import mic_recorder

# --- ページ基本設定 ---
st.set_page_config(page_title="英語音読・発音判定AI", page_icon="🎤")

st.title("🎤 英語音読・発音判定アプリ")
st.caption("即興で読んだ英文や、課題の英文を入力して音読を録音・アップロードしてみよう！")

# --- 1. APIキーの読み込み ---
api_key = st.secrets.get("GEMINI_API_KEY")

if not api_key:
    st.error("APIキーが設定されていません。StreamlitのSecretsに「GEMINI_API_KEY」を設定してください。")
    st.stop()

client = genai.Client(api_key=api_key)

# --- 2. 利用可能なモデルの自動検出 ＆ 優先順位リスト作成 ---
@st.cache_resource
def get_available_candidate_models():
    try:
        # APIから実際に利用可能なモデル一覧を取得
        models_list = list(client.models.list())
        available_names = [m.name.replace("models/", "") for m in models_list]
        
        # 1.5-flashの後継である「flash-lite」を最優先に指定
        priority_keywords = [
            "gemini-2.5-flash-lite",  # 最優先（旧1.5-flashに相当する軽量・制限制限が緩いモデル）
            "gemini-2.0-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.0-flash"
        ]
        
        candidates = []
        for kw in priority_keywords:
            for name in available_names:
                if kw in name and name not in candidates:
                    candidates.append(name)
        
        # リストになかったモデルも予備として追加
        for name in available_names:
            if "gemini" in name and name not in candidates:
                candidates.append(name)
                
        return candidates if candidates else ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
    except Exception:
        # 万が一モデル一覧取得に失敗した場合は軽量モデルを標準設定
        return ["gemini-2.5-flash-lite", "gemini-2.5-flash"]

candidate_models = get_available_candidate_models()

# サイドバーに自動検出された候補モデルを表示
st.sidebar.title("⚙️ 設定情報")
st.sidebar.info(f"🤖 使用候補モデル順:\n" + "\n".join([f"- `{m}`" for m in candidate_models[:3]]))

# --- 3. UIの構築 ---
st.subheader("1. 音読する英文を入力")
target_sentence = st.text_area(
    "読んだ（または読む予定の）英文を入力してください:",
    value="I like playing soccer with my friends.",
    height=100
)

st.subheader("2. 音声の準備（どちらか一方）")
tab1, tab2 = st.tabs(["🎤 ブラウザで直接録音", "📁 音声ファイルをアップロード"])

audio_bytes = None
audio_file_name = "speech.wav"

with tab1:
    st.write("下のマイクボタンを押して録音を開始し、読み終わったら再度押して停止してください。")
    audio_output = mic_recorder(
        start_prompt="🔴 録音開始",
        stop_prompt="⬛ 録音停止",
        key='recorder'
    )
    if audio_output:
        audio_bytes = audio_output['bytes']
        st.audio(audio_bytes, format='audio/wav')
        st.success("録音が完了しました！")

with tab2:
    uploaded_file = st.file_uploader("録音データ（.mp3, .wav, .m4a, .webm など）を選択", type=["mp3", "wav", "m4a", "webm", "ogg"])
    if uploaded_file is not None:
        audio_bytes = uploaded_file.read()
        audio_file_name = uploaded_file.name
        st.audio(audio_bytes)

st.divider()

# --- 4. 判定処理 ---
if st.button("🚀 音読を判定する", type="primary", use_container_width=True):
    if not target_sentence.strip():
        st.warning("英文を入力してください。")
    elif not audio_bytes:
        st.warning("音声データを録音するか、ファイルをアップロードしてください。")
    else:
        with st.spinner("🤖 Geminiが音声を聞いて添削中... 数秒お待ちください"):
            tmp_path = None
            audio_file = None
            
            try:
                # 一時ファイルとして音声データを保存
                ext = os.path.splitext(audio_file_name)[1]
                if not ext:
                    ext = ".wav"
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
                    tmp_file.write(audio_bytes)
                    tmp_path = tmp_file.name

                # Geminiへ音声ファイルをアップロード
                audio_file = client.files.upload(file=tmp_path)

                # 評価プロンプト
                prompt = f"""
あなたは中学校の親しみやすい熱血英語コーチであり、発音矯正のプロフェッショナルである「Gemini先生」です。
生徒が以下の【お手本英文】を音読しました。
添付された音声ファイルを聴き、**「指定された単語を正確に読めているか」「ネイティブに正しく伝わるか」**という基準で厳しくチェックしつつ、**生徒のやる気を引き出す温かい指導**を行ってください。

【お手本英文】: "{target_sentence}"

---
### ⚠️ 採点・判定ルール（厳密に適用してください）

0. **【最重要】ハルシネーション（自動補正・推測）の絶対禁止**:
   - **音声を聴く際、【お手本英文】を一旦無視し、耳だけで聴こえた通りの音を文字起こししてください。**
   - 雑音が多い、声が小さすぎる、途切れているなどの理由で**音声が不鮮明で判別できない場合、勝手に「お手本通り読んだのだろう」と推測・補正して評価しないでください。**
   - 音声が不鮮明で聞き取れない単語がある場合は、AI Checkに `[聞き取り不能/unclear]` と記載し、無理に高得点をつけず「もう一度静かな場所でハッキリ録音してみよう！」とアドバイスしてください。

1. **単語の誤読・言い間違いの厳罰化**:
   - お手本英文と異なる単語を言っている場合（例: `soccer` を `baseball`、`friends` を `family` と誤読）、または単語を丸ごと抜かしている場合は、発音の正確さを【0〜5点/25点満点】とし、総合スコアは【50点未満】に落としてください。

2. **レベルに応じた明確な採点・判定**:
   - **【90〜100点（ネイティブレベル）】**: 【お手本英文】の単語をすべて正確に音読しており、カタカナ感がほぼなく、音の繋がりや強弱が自然な場合。
   - **【70〜89点（標準・伝わるレベル）】**: 単語はすべて合っているが、カタカナ感や平坦さが少し残る場合。
   - **【50〜69点（カタカナ・日本語英語レベル）】**: 単語は合っているが、単語ごとにブツ切り、「ライク [raiku]」のように余計な母音（u, o）が入る場合。
   - **【50点未満（単語誤読・不鮮明・重大なエラー）】**: 指定と異なる単語を発音している、音声が小さく不鮮明で聞き取れない、または日本語読みが露骨すぎる場合。

3. **減点・評価のチェックポイント**:
   - **音声の鮮明さ・単語の言い間違い・読み飛ばし（最優先チェック）**
   - 子音の後の無駄な母音（uやoなど）の足し込み（例: "like" → "ライク"）
   - `th`（サ/シ）、`f/v`（ハ/バ）、`r/l`（ラ）の代用
   - 日本語特有の「平坦で一本調子な音調」や「単語ごとのブツ切り」
   ※ただし、正確に発音されているネイティブ特有の滑らかな音の変化や息の抜け方を「誤読」や「無駄な母音」と誤判定しないよう注意してください。

4. **指導のトーン・マインド**:
   - 言い間違いやカタカナ発音には厳しく採点しますが、言葉遣いは絶対に冷たくせず、**「声の大きさやチャレンジした姿勢などを具体的に1つ褒める」**こと。
   - 音声が聞き取れなかった場合は「もう少しマイクの近くで大きな声で録音してみよう！」と前向きに再録音を促してください。

---
### 🏁 出力フォーマット（以下の形式・見出しを厳守してください）

### 🌟 今日の音読ランク: [🌟🌟🌟 (星1〜3個) / 称号: 例「クリア発音マスター」「チャレンジャー」など]
**🎯 総合スコア: [点数]点 / 100点**

#### 📊 観点別評価 (各25点満点)
* **発音の正確さ [ /25点]**: （不鮮明さがないか、言い間違いがないか、個々の単語の発音や無駄な母音の混入がないか）
* **リズム・流暢さ [ /25点]**: （詰まりやスピード、日本語特有の平坦な音調になっていないか）
* **イントネーション [ /25点]**: （文末の上げ下げや強調、強弱のつけ方が自然か）
* **リンキング [ /25点]**: （単語と単語のつながり、音がくっついて英語らしくできているか）

#### 👏 ここが素晴らしい！ (Great Job!)
* (具体的に聞こえた良いポイントや、しっかり言えていた単語・声の大きさを1〜2点挙げて褒める)

#### 🎧 聞き取り添削 (AI Check)
* **AIが実際に聴き取った英文**: (実際に発音されていた音通りにテキスト化。聞こえない部分は [聞き取り不能] と明記)

#### 🔍 カタカナ英語・言い間違いのチェック結果
* **🚨 改善が必要な単語**:
  * (不鮮明な場合例: `soccer` → 実際の発音: 「[聞き取り不能]」 / 判定: 音声が小さく/雑音で判断できません)
  * (言い間違いの場合例: `soccer` → 実際の発音: 「baseball [ベースボール]」 / 判定: `soccer` ではなく `baseball` と言っています)
  * (発音ミスの場合例: `playing` → 実際の発音: 「プレイング [pureingu]」 / 判定: 「p」の後に「ウ」が混ざってカタカナになっている)
  *(※90点以上の場合は「特になし！ネイティブ通りの素晴らしい発音です！」とする)*

#### 💡 ネイティブ発音に近づくワンポイントアドバイス (Next Step)
*(※一番直したい重要な1〜2点に絞って解説)*
* **[対象の単語]**: 
  * 指摘内容: (不鮮明さの指摘、言い間違いの指摘、またはカタカナに聞こえる理由)
  * 対策・コツ: 「（マイクとの距離の調整、正しい単語の確認、または中学生がすぐ真似できる口や舌の動かし方）」

#### 🗣️ 先生からの応援メッセージ
(点数に応じたアドバイスと、「次はこの単語に気をつけて読んでみよう！」「もう一度静かなところで録音してみよう！」と次に向けて前向きになれるメッセージ)
"""

                response = None
                used_model = None
                last_error = None

                # 404（未存在）や429（上限オーバー）でも止まらず次の有効モデルを自動試行
                for model_name in candidate_models:
                    try:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=[audio_file, prompt]
                        )
                        used_model = model_name
                        break  # 成功したらループを抜ける
                    except Exception as e:
                        last_error = e
                        continue  # エラー発生時は次の候補モデルを試す

                if response:
                    st.success(f"添削が完了しました！（使用モデル: `{used_model}`）")
                    st.markdown(response.text)
                else:
                    st.error(f"利用可能なモデルの呼び出しに失敗しました: {last_error}")

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
            
            finally:
                # 一時ファイルとサーバー上データのクリーンアップ
                if audio_file:
                    try:
                        client.files.delete(name=audio_file.name)
                    except Exception:
                        pass
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)
