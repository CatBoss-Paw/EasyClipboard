"""PromptsStore 存储层回归测试（隔离临时根目录，绝不触碰真实数据）。"""
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="prompts_store_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prompts_store import PromptsStore, clean_name, default_doc_name  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}  {detail}")


store = PromptsStore(TMP / "_Prompts")

# ---- 命名清洗 ----
check("非法字符清洗", clean_name('a/b\\c:d*e?f"g<h>i|j') == "a b c d e f g h i j")
check("空白降级", clean_name("   ") == "未命名")
check("默认名取首行", default_doc_name("\n\n这是首行内容\n第二行") == "这是首行内容")
check("默认名超20字截断", default_doc_name("x" * 50) == "x" * 20)

# ---- 分类 CRUD ----
check("新建分类", store.ensure_folder("工作") == "工作")
store.ensure_folder("学习")
store.ensure_folder("工作")              # 幂等
check("分类列表", store.folders() == ["学习", "工作"], repr(store.folders()))
check("分类重命名", store.rename_folder("学习", "研究") == "研究")
check("重命名后列表", "研究" in store.folders() and "学习" not in store.folders())
check("空分类可删", store.delete_folder("研究") is True)
check("删除后列表", "研究" not in store.folders())

# ---- 文档 CRUD ----
p1 = store.add_text("你是起名大师。请为品牌起 5 个名字……", "工作")
check("入库默认名=首行前20字", p1.stem == "你是起名大师。请为品牌起 5 个名字……", repr(p1.stem))
check("文档存在", p1.is_file() and p1.read_text(encoding="utf-8").startswith("你是起名大师"))
p2 = store.add_text("同名测试", "工作", name=p1.stem)
check("重名自动加序号", p2.stem.endswith("_2"), repr(p2.stem))

docs = store.docs("工作")
check("文档列表 2 条", len(docs) == 2, f"docs={len(docs)}")
check("预览与字数", any(d["preview"].startswith("你是起名大师") and d["chars"] > 10
                        for d in docs), repr(docs))

# ---- 改名/编辑/置顶/移动/删除 ----
new_name = store.rename_doc("工作", p1.stem, "起名神器")
check("文档改名", new_name == "起名神器" and (TMP / "_Prompts/工作/起名神器.md").is_file())

store.write_doc("工作", "起名神器", "改后的内容")
check("编辑内容", store.read_doc("工作", "起名神器") == "改后的内容")

check("文档置顶", store.toggle_doc_pin("工作", "起名神器") is True)
docs = store.docs("工作")
check("置顶后第一个", docs[0]["name"] == "起名神器" and docs[0]["pinned"])

store.move_doc("工作", "起名神器", "学习")
check("移动分类", (TMP / "_Prompts/学习/起名神器.md").is_file()
      and not (TMP / "_Prompts/工作/起名神器.md").exists())
check("原分类剩 1 条", len(store.docs("工作")) == 1)

check("非空分类不可删", store.delete_folder("学习") is False)
store.delete_doc("学习", "起名神器")
check("删除文档", not (TMP / "_Prompts/学习/起名神器.md").exists())
check("空后分类可删", store.delete_folder("学习") is True)

# ---- 分类置顶 ----
store.ensure_folder("A类")
store.ensure_folder("B类")
store.toggle_folder_pin("B类")
check("置顶分类排最前", store.folders()[0] == "B类", repr(store.folders()))

# ---- 索引与时实一致性（root 被外部塞了文件） ----
(TMP / "_Prompts/手工分类").mkdir(exist_ok=True)
(TMP / "_Prompts/手工分类/手工.md").write_text("x", encoding="utf-8")
check("外部手工分类对账可见", "手工分类" in store.folders())
check("手工文档可见", any(d["name"] == "手工" for d in store.docs("手工分类")))

print(f"\n=== 结果: {PASS} PASS, {FAIL} FAIL ===")
sys.exit(0 if FAIL == 0 else 1)
