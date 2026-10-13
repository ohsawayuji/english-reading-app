import os
import tempfile
import streamlit as st
from google import genai
from streamlit_mic_recorder import mic_recorder

st.set_page_config(page_title="英語音読・発音判定AI", page_icon="🎤")

st.title("🎤 英語音読・発音判定アプリ")
st.caption("即興で読んだ英文や、課題の英文を入力して音読を録音・アップロードしてみよう！")

# --- 1. APIキーの読み込み ---
api_key = st.secrets.get("GEMINI_API_KEY")

if not api_key:
    st.error("APIキーが設定されていません。StreamlitのSecretsに「GEMINI_API_KEY」を設定してください。")
    st.stop()

client = genai.Client(api_key=api_key)

# --- 2. モデルの自動選択 ---
@st.cache_resource
def get_target_model():
    available_models = [m.name for m in client.models.list()]
    model_names = [m.replace("models/", "") for m in available_models]
    
    for priority_model in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]:
        if priority_model in model_names:
            return priority_model
    return model_names[0]

target_model = get_target_model()

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
    uploaded_file = st.file_uploader("録音データ（.mp3, .wav, .m4aなど）を選択", type=["mp3", "wav", "m4a"])
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
            try:
                # 一時ファイルとして音声データを保存
                ext = os.path.splitext(audio_file_name)[1]
                if not ext:
                    ext = ".wav"
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
                    tmp_file.write(audio_bytes)
                    tmp_path = tmp_file.name

                # Geminiへアップロード
                audio_file = client.files.upload(file=tmp_path)

                prompt = f"""
あなたは中学校の親しみやすい熱血英語コーチであり、発音矯正のプロフェッショナルである「Gemini先生」です。
生徒が以下の【読んだ英文】を音読しました。
添付された音声ファイルを聴き、**「ネイティブに正しく伝わるか」という基準**で公平に評価しつつ、**生徒のやる気を引き出す温かい指導**を行ってください。

【生徒が読んだ英文】: "{target_sentence}"

---
### ⚠️ 採点・判定ルール（厳密に適用してください）

1. **レベルに応じた明確な採点・判定**:
   - **【90〜100点（ネイティブレベル）】**: カタカナ感がほぼなく、余計な母音混入がない。音の繋がり（リンキング）や強弱（ストレス）が自然で滑らかな場合。
   - **【70〜89点（標準・伝わるレベル）】**: カタカナ感や平坦さが少し残るが、スムーズで十分伝わる音読。
   - **【50〜69点（カタカナ・日本語英語レベル）】**: 単語ごとにブツ切り、「ライク [raiku]」のように子音の後ろに余計な母音（u, o）が入る、お経のように平坦で一本調子な音読。
   - **【50点未満】**: 英文と異なる発音、または日本語読みが露骨すぎて英語として認識しづらいレベル。

2. **減点・評価のチェックポイント**:
   - 子音の後の無駄な母音（uやoなど）の足し込み（例: "like" → "ライク"）
   - `th`（サ/シ）、`f/v`（ハ/バ）、`r/l`（ラ）の代用
   - 日本語特有の「平坦で一本調子な音調」や「単語ごとのブツ切り（リンキング欠如）」
   ※ただし、**ネイティブ特有の滑らかな音の変化や息の抜け方を「無駄な母音」や「崩れ」と誤判定して減点しないよう注意**してください。

3. **指導のトーン・マインド**:
   - 採点基準はブレずに適用しますが、言葉遣いは絶対に冷たくせず、**「まず良かったところを具体的に1つ褒める」**こと。
   - 改善点は欲張らず**最も重要な1〜2点**に絞り、カタカナ表記と簡単な口の動き（「口を横に広げて」「舌を上の歯につけて」など）でわかりやすくアドバイスしてください。

---
### 🏁 出力フォーマット（以下の形式・見出しを厳守してください）

### 🌟 今日の音読ランク: [🌟🌟🌟 (星1〜3個) / 称号: 例「クリア発音マスター」「ノリノリ・リズム名人」など]
**🎯 総合スコア: [点数]点 / 100点**

#### 📊 観点別評価 (各25点満点)
* **発音の正確さ [ /25点]**: （個々の単語の発音や、カタカナ発音・無駄な母音の混入がないか）
* **リズム・流暢さ [ /25点]**: （詰まりやスピード、日本語特有の平坦な音調になっていないか）
* **イントネーション [ /25点]**: （文末の上げ下げや強調、強弱のつけ方が自然か）
* **リンキング [ /25点]**: （単語と単語のつながり、音がくっついて英語らしくできているか）

#### 👏 ここが素晴らしい！ (Great Job!)
* (具体的に聞こえた良いポイントや、しっかり言えていた単語・音を1〜2点挙げて褒める)

#### 🎧 聞き取り添削 (AI Check)
* **AIが実際に聴き取った英文**: (実際に発音されていた音通りにテキスト化)

#### 🔍 カタカナ英語・日本語発音のチェック結果
* **🚨 改善が必要な単語**:
  * (例: `playing` → 実際の発音: 「プレイング [pureingu]」 / 判定: 「p」の後に「ウ」が混ざってカタカナになっている)
  *(※90点以上の場合は「特になし！ネイティブ通りの素晴らしい発音です！」とする)*

#### 💡 ネイティブ発音に近づくワンポイントアドバイス (Next Step)
*(※一番直したい重要な1〜2点に絞って解説)*
* **[対象の単語]**: 
  * なぜカタカナに聞こえるか: 
  * 舌・口の動かし方のコツ: 「（中学生がすぐ真似できる口や舌の動かし方）」

#### 🗣️ 先生からの応援メッセージ
(点数に応じたアドバイスと、「ここを直せばもっとカッコよくなるよ！」「この調子で頑張ろう！」と次に向けて前向きになれるメッセージ)
"""

                response = client.models.generate_content(
                    model=target_model,
                    contents=[audio_file, prompt]
                )

                # クリーンアップ
                client.files.delete(name=audio_file.name)
                os.remove(tmp_path)

                st.success("添削が完了しました！")
                st.markdown(response.text)

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
