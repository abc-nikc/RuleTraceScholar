"""PDF parsing and integration with RAG system."""

from pathlib import Path
import uuid
import re
from typing import Optional, Any
from docling.document_converter import DocumentConverter
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from .models import PaperNode, NodeType
from .node_generator import NodeContentGeneratorFactory, TableGenerator
from .factory import EmbeddingService, MilvusStoreFactory

FIGURE_SAVE_DIR = Path("./data/figures")


def classify_section_title(title: str) -> str:
    """Deterministic fallback for local models that cannot return structured output.

    Section routing is a retrieval control, so silently labelling an entire paper
    as ``other`` is worse than using a conservative heading heuristic.
    """
    normalized = re.sub(r"^\s*\d+(?:\.\d+)*[.)]?\s*", "", title or "").strip().lower()
    if not normalized:
        return "other"

    patterns = (
        ("experiment", (
            "experiment", "evaluation", "result", "ablation", "benchmark",
            "performance", "case study", "implementation", "setup", "statistics",
            "cost-quality", "human evaluation", "实验", "结果",
            "消融", "评估", "性能", "案例分析",
        )),
        ("method", (
            "method", "methodology", "approach", "architecture", "framework",
            "model", "algorithm", "system design", "pipeline", "retrieval",
            "construction", "inference", "scoring", "verification", "synthesis",
            "pruning", "provenance", "abstraction", "generation", "complexity",
            "pseudo-code", "pseudocode", "方法", "模型",
            "架构", "框架", "算法", "系统设计",
        )),
        ("conclusion", (
            "conclusion", "discussion", "limitation", "future work", "outlook",
            "threats to validity", "结论", "讨论", "局限", "限制", "未来工作",
            "展望",
        )),
        ("background", (
            "abstract", "introduction", "background", "motivation", "related work",
            "preliminar", "literature review", "overview", "摘要", "引言", "背景",
            "动机", "相关工作", "预备知识", "概述",
        )),
    )
    compact = re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized)
    for section_type, keywords in patterns:
        if any(
            keyword in normalized
            or re.sub(r"[^\w\u4e00-\u9fff]+", "", keyword) in compact
            for keyword in keywords
        ):
            return section_type
    return "other"


class TextCleaner:
    """Clean and normalize text content."""

    @staticmethod
    def clean_text(text: str) -> str:
        """Remove extra whitespace and normalize text."""
        text = re.sub(r'-\n', '', text)
        text = re.sub(r'\n+', '\n', text)
        text = re.sub(r' +', ' ', text)
        return text.strip()

    @staticmethod
    def is_header_footer(text: str, page_height: float, bbox: Optional[tuple]) -> bool:
        """Detect if text is likely header/footer based on position."""
        if not bbox or len(bbox) != 4:
            return False
        _, top, _, bottom = bbox
        margin_threshold = page_height * 0.1
        return top < margin_threshold or bottom > (page_height - margin_threshold)

    @staticmethod
    def is_page_number(text: str) -> bool:
        """Detect if text is a page number."""
        return bool(re.match(r'^\d+$', text.strip()))


class PDFParser:
    """Parse PDF documents into PaperNode structures."""

    def __init__(self, figure_save_dir: Optional[Path] = None, llm=None):
        self.cleaner = TextCleaner()
        self._converter_cache = {}
        self.figure_save_dir = figure_save_dir or FIGURE_SAVE_DIR
        self.llm = llm

    def parse(self, pdf_path: str, paper_id: str) -> list[PaperNode]:
        """Parse PDF file into list of PaperNodes.
        
        Args:
            pdf_path: Path to PDF file
            paper_id: Unique identifier for the paper
            
        Returns:
            List of PaperNode objects
        """
        nodes = self._parse_with_ocr(pdf_path, paper_id, use_ocr=False)
        
        total_text = sum(len(n.text) for n in nodes)
        page_count = max((n.page_num for n in nodes), default=1)
        
        if total_text < 1000 or total_text / page_count < 200:
            print(f"Low text detected ({total_text} chars, {page_count} pages), retrying with OCR...")
            nodes = self._parse_with_ocr(pdf_path, paper_id, use_ocr=True)
        
        return nodes
    
    def _parse_with_ocr(self, pdf_path: str, paper_id: str, use_ocr: bool) -> list[PaperNode]:
        """Internal parse with OCR option."""
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        
        if use_ocr not in self._converter_cache:
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = use_ocr
            self._converter_cache[use_ocr] = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
        
        converter = self._converter_cache[use_ocr]
        result = converter.convert(pdf_path)
        doc = result.document
        self._fitz_doc = None  # reset per parse call
        
        page_height = self._get_page_height(doc)
        
        raw_items = [item for item, _ in doc.iterate_items()]
        filtered_items = self._filter_items(raw_items, page_height)
        sorted_items = self._sort_reading_order(filtered_items)
        top_level_x = self._compute_top_level_x(sorted_items)
        
        nodes = []
        order = 0
        section_stack = []
        
        for item in sorted_items:
            node = self._process_item(
                item, paper_id, order, section_stack, top_level_x
            )
            if node:
                nodes.append(node)
                order += 1
        
        self._link_captions_to_figures_tables(nodes)
        self._link_text_references(nodes)
        self._extract_figure_images(pdf_path, doc, nodes)
        self._classify_sections(nodes)
        
        return nodes

    def _get_page_height(self, doc) -> float:
        """Extract page height from document."""
        if hasattr(doc, 'pages') and doc.pages:
            try:
                if isinstance(doc.pages, dict):
                    first_page = next(iter(doc.pages.values()))
                else:
                    first_page = doc.pages[0]
                
                if hasattr(first_page, 'size') and hasattr(first_page.size, 'height'):
                    return first_page.size.height
            except (KeyError, IndexError, StopIteration):
                pass
        return 792.0

    def _filter_items(self, items: list[Any], page_height: float) -> list[Any]:
        """Filter out headers, footers, and page numbers."""
        filtered = []
        
        for item in items:
            if not hasattr(item, 'text'):
                filtered.append(item)
                continue
            
            text = item.text.strip()
            if not text:
                orig = getattr(item, 'orig', None)
                if orig and orig.strip():
                    filtered.append(item)
                continue
            
            bbox = self._extract_bbox(item)
            
            if self.cleaner.is_page_number(text):
                continue
            
            if bbox and self.cleaner.is_header_footer(text, page_height, bbox):
                continue
            
            filtered.append(item)
        
        return filtered

    def _sort_reading_order(self, items: list[Any]) -> list[Any]:
        """Preserve Docling's document reading order.

        ``iterate_items`` already emits layout-aware reading order. Re-sorting every
        page by horizontal rows interleaves the left and right columns of academic
        PDFs, which can attach method text to Related Work and corrupt retrieval.
        """
        return list(items)
    
    def _estimate_row_tolerance(self, items_with_bbox: list[tuple]) -> float:
        """Estimate vertical tolerance for grouping items into rows."""
        heights = [abs(bbox[1] - bbox[3]) for _, bbox in items_with_bbox if bbox]
        if not heights:
            return 10.0
        avg_height = sum(heights) / len(heights)
        return max(avg_height * 0.6, 5.0)
    
    def _group_into_rows(self, items_with_bbox: list[tuple], tolerance: float) -> list[list[tuple]]:
        """Group items into rows based on vertical proximity."""
        sorted_by_y = sorted(items_with_bbox, key=lambda x: -x[1][1])
        
        rows = []
        for item, bbox in sorted_by_y:
            placed = False
            for row in rows:
                row_y = row[0][1][1]
                if abs(bbox[1] - row_y) <= tolerance:
                    row.append((item, bbox))
                    placed = True
                    break
            if not placed:
                rows.append([(item, bbox)])
        
        rows.sort(key=lambda r: -r[0][1][1])
        return rows

    def _process_item(
        self,
        item,
        paper_id: str,
        order: int,
        section_stack: list[str],
        top_level_x: float
    ) -> Optional[PaperNode]:
        """Process a single document item into a PaperNode."""
        item_type = type(item).__name__
        raw_text = item.text if hasattr(item, 'text') else ""
        if not raw_text and hasattr(item, 'orig') and item.orig:
            raw_text = item.orig
        raw_text = self.cleaner.clean_text(raw_text)
        
        if self._is_caption_text(raw_text):
            node_type = "caption"
        else:
            node_type = self._map_item_type(item_type)
        
        if not node_type:
            return None
        
        node_id = str(uuid.uuid4())
        page_num = item.prov[0].page_no if item.prov and len(item.prov) > 0 else 0
        bbox = self._extract_bbox(item) if node_type in ["figure", "table", "caption"] else None
        
        if node_type == "section_header":
            item_bbox = self._extract_bbox(item)
            self._update_section_stack(section_stack, raw_text, item_bbox, top_level_x)
        
        generator = NodeContentGeneratorFactory.get_generator(node_type)
        
        node = PaperNode(
            node_id=node_id,
            paper_id=paper_id,
            node_type=node_type,
            text="",
            page_num=page_num,
            order=order,
            section_path=section_stack.copy(),
            bbox=bbox
        )
        
        if node_type == "table":
            node.metadata["item"] = item
        
        context = {"raw_text": raw_text, "item": item}
        node.text = generator.generate_text(node, raw_text, context)
        
        return node

    def _map_item_type(self, item_type: str) -> Optional[NodeType]:
        """Map Docling item type to NodeType."""
        mapping = {
            "SectionHeaderItem": "section_header",
            "TextItem": "paragraph",
            "ListItem": "paragraph",
            "TableItem": "table",
            "PictureItem": "figure",
            "FormulaItem": "formula",
        }
        return mapping.get(item_type)

    def _is_caption_text(self, text: str) -> bool:
        """Check if text is a caption based on pattern."""
        if not text:
            return False
        text = text.strip()
        return bool(re.match(r'^(Caption:\s*)?(Figure|Table|Fig\.|Tab\.)\s+\d+', text, re.IGNORECASE))

    def _extract_bbox(self, item) -> Optional[tuple[float, float, float, float]]:
        """Extract bounding box from item."""
        if hasattr(item, 'self_ref') and item.self_ref:
            ref = item.self_ref
            if hasattr(ref, 'bbox') and ref.bbox:
                bbox = ref.bbox
                return (bbox.l, bbox.t, bbox.r, bbox.b)
        
        if hasattr(item, 'prov') and item.prov and len(item.prov) > 0:
            prov = item.prov[0]
            if hasattr(prov, 'bbox') and prov.bbox:
                bbox = prov.bbox
                return (bbox.l, bbox.t, bbox.r, bbox.b)
        
        if hasattr(item, 'bbox') and item.bbox:
            bbox = item.bbox
            return (bbox.l, bbox.t, bbox.r, bbox.b)
        
        return None

    def _compute_top_level_x(self, items: list[Any]) -> float:
        """Compute minimum left-edge x of all section headers as top-level baseline."""
        xs = []
        for item in items:
            if type(item).__name__ == 'SectionHeaderItem':
                bbox = self._extract_bbox(item)
                if bbox:
                    xs.append(bbox[0])
        return min(xs) if xs else 0.0

    def _is_top_level_section(self, header_text: str, bbox, top_level_x: float) -> bool:
        """Determine if a section header is top-level via numeric prefix or x position."""
        num_match = re.match(r'^(\d+(?:\.\d+)*)\s+', header_text)
        if num_match:
            # A numbered top-level heading can begin in the right column after
            # the previous section ends. Horizontal position must not demote it.
            return len(num_match.group(1).split('.')) == 1
        return True

    def _update_section_stack(self, section_stack: list[str], header_text: str, bbox, top_level_x: float):
        """Update section stack, keeping only the top-level section."""
        if self._is_top_level_section(header_text, bbox, top_level_x):
            section_stack[:] = [header_text]

    def _linearize_table(self, item) -> str:
        """Linearize table into key-value format."""
        if not hasattr(item, 'data') or not item.data:
            return ""
        
        data = item.data
        if not hasattr(data, 'table_cells') or not data.table_cells or len(data.table_cells) == 0:
            return ""
        
        try:
            cells = data.table_cells
            rows_dict = {}
            for cell in cells:
                row_idx = cell.start_row_offset_idx if hasattr(cell, 'start_row_offset_idx') else 0
                col_idx = cell.start_col_offset_idx if hasattr(cell, 'start_col_offset_idx') else 0
                text = cell.text if hasattr(cell, 'text') else str(cell)
                
                if row_idx not in rows_dict:
                    rows_dict[row_idx] = {}
                rows_dict[row_idx][col_idx] = text
            
            if not rows_dict:
                return ""
            
            sorted_rows = sorted(rows_dict.items())
            headers = [sorted_rows[0][1].get(i, "") for i in range(max(sorted_rows[0][1].keys()) + 1)] if sorted_rows else []
            rows = [[row_data.get(i, "") for i in range(max(row_data.keys()) + 1)] for _, row_data in sorted_rows[1:]]
            
            if not headers:
                return ""
                
        except (AttributeError, IndexError, TypeError, KeyError) as e:
            return ""
        
        return TableGenerator.linearize_table(headers, rows)

    def _link_captions_to_figures_tables(self, nodes: list[PaperNode]):
        """Link captions to their corresponding figures/tables."""
        for node in nodes:
            if node.node_type in ["figure", "table"]:
                caption_type = "Figure" if node.node_type == "figure" else "Table"
                caption_text = self._find_caption_for_node(node, nodes, caption_type)
                if caption_text:
                    generator = NodeContentGeneratorFactory.get_generator(node.node_type)
                    context = {"caption_text": caption_text}
                    if node.node_type == "table" and 'item' in node.metadata:
                        linearized = self._linearize_table(node.metadata['item'])
                        if linearized:
                            context["linearized_table"] = linearized
                    node.text = generator.generate_text(node, "", context)

    
    def _find_caption_for_node(self, node: PaperNode, nodes: list[PaperNode], caption_type: str) -> str:
        """Find caption for a figure/table node."""
        if not node.bbox:
            return ""
        
        best_caption = ""
        min_distance = float('inf')
        
        for other in nodes:
            if other.node_type == "caption" and other.page_num == node.page_num:
                if caption_type.lower() in other.text.lower():
                    if other.bbox:
                        distance = abs(other.bbox[1] - node.bbox[1])
                        if distance < min_distance and distance < 300:
                            min_distance = distance
                            best_caption = other.text
        
        return best_caption

    def _link_text_references(self, nodes: list[PaperNode]):
        """Link paragraphs to figures/tables they reference in text."""
        fig_table_index: dict[tuple[str, str], PaperNode] = {}
        for node in nodes:
            if node.node_type in ["figure", "table", "caption"]:
                match = re.search(r'(Figure|Table)\s+(\d+)', node.text, re.IGNORECASE)
                if match:
                    key = (match.group(1).lower(), match.group(2))
                    if key not in fig_table_index:
                        fig_table_index[key] = node

        for node in nodes:
            if node.node_type not in ["paragraph", "formula"]:
                continue
            for match in re.finditer(r'(Figure|Table)\s+(\d+)', node.text, re.IGNORECASE):
                key = (match.group(1).lower(), match.group(2))
                target = fig_table_index.get(key)
                if target and target.node_id not in node.related_ids:
                    node.related_ids.append(target.node_id)
                    if node.node_id not in target.related_ids:
                        target.related_ids.append(node.node_id)

    def _extract_figure_images(self, pdf_path: str, doc, nodes: list[PaperNode]):
        """Crop and save figure images using pymupdf based on bbox.

        PDF coordinate system (pymupdf): origin top-left, y increases downward.
        Docling bbox: (l, t, r, b) where t > b (origin bottom-left).
        We convert via: fitz_y = page_height - docling_y.
        """
        try:
            import fitz  # pymupdf
        except ImportError:
            print("pymupdf not installed, skipping figure image extraction.")
            return

        figure_nodes = [n for n in nodes if n.node_type == "figure" and n.bbox and n.page_num]
        if not figure_nodes:
            return

        try:
            fitz_doc = fitz.open(pdf_path)
        except Exception as e:
            print(f"Failed to open PDF with pymupdf: {e}")
            return

        paper_id = figure_nodes[0].paper_id
        save_dir = self.figure_save_dir / paper_id
        save_dir.mkdir(parents=True, exist_ok=True)

        # Build page height map from fitz (points)
        page_heights = {i: fitz_doc[i].rect.height for i in range(len(fitz_doc))}

        for node in figure_nodes:
            page_idx = node.page_num - 1  # fitz is 0-indexed
            if page_idx < 0 or page_idx >= len(fitz_doc):
                continue

            page = fitz_doc[page_idx]
            ph = page_heights[page_idx]

            # Docling bbox: (l, t, r, b) in PDF points, origin bottom-left
            l, t, r, b = node.bbox
            # Convert to fitz (origin top-left)
            fitz_rect = fitz.Rect(l, ph - t, r, ph - b)
            # Add small padding
            fitz_rect = fitz_rect + fitz.Rect(-4, -4, 4, 4)
            fitz_rect = fitz_rect & page.rect  # clamp to page

            if fitz_rect.is_empty or fitz_rect.is_infinite:
                continue

            try:
                mat = fitz.Matrix(2.0, 2.0)  # 2x DPI for clarity
                clip = page.get_pixmap(matrix=mat, clip=fitz_rect)
                img_path = save_dir / f"page{node.page_num}_order{node.order}.png"
                clip.save(str(img_path))
                node.image_path = str(img_path)
            except Exception as e:
                print(f"Failed to crop figure {node.node_id}: {e}")

        fitz_doc.close()

    def _classify_sections(self, nodes: list[PaperNode]):
        """Classify headers deterministically so indexing never depends on an LLM call."""
        section_nodes = [n for n in nodes if n.node_type == "section_header"]
        if not section_nodes:
            return

        titles = [n.text.replace("Section: ", "").strip() for n in section_nodes]
        title_to_type = {title: classify_section_title(title) for title in titles}

        section_type_by_title = {}
        for node in section_nodes:
            title = node.text.replace("Section: ", "").strip()
            section_type = title_to_type.get(title, classify_section_title(title))
            node.metadata["section_type"] = section_type
            section_type_by_title[title] = section_type

        for node in nodes:
            if node.node_type == "section_header":
                continue
            node.metadata["section_type"] = "other"
            for section_title in reversed(node.section_path):
                if section_title in section_type_by_title:
                    node.metadata["section_type"] = section_type_by_title[section_title]
                    break


class RAGIntegration:
    """Convert nodes to documents and store in Milvus with hybrid retrieval."""
    
    def __init__(
        self,
        embedding_model: str = "BAAI/bge-small-en-v1.5",
        milvus_uri: str = "http://localhost:19530",
        collection_name: str = "papers"
    ):
        self.embeddings = EmbeddingService.get_embeddings(embedding_model)
        self.milvus_uri = milvus_uri
        self.collection_name = collection_name
    
    def nodes_to_documents(self, nodes: list[PaperNode]) -> list[Document]:
        """Convert PaperNodes to LangChain Documents."""
        docs = []
        for node in nodes:
            if not node.text.strip():
                continue
            
            metadata = {
                "node_id": node.node_id,
                "paper_id": node.paper_id,
                "node_type": node.node_type,
                "page_num": node.page_num,
                "order": node.order,
                "section_path": " > ".join(node.section_path) if node.section_path else "",
                "section_type": node.metadata.get("section_type", "other"),
            }
            if node.bbox:
                metadata["bbox"] = str(node.bbox)
            if node.parent_id:
                metadata["node_parent_id"] = node.parent_id
            if node.image_path:
                metadata["image_path"] = node.image_path
            # vlm_description starts empty; populated lazily at query time
            metadata["vlm_description"] = node.metadata.get("vlm_description", "")

            metadata.update({k: v for k, v in node.metadata.items() if k != "item"})
            
            docs.append(Document(page_content=node.text, metadata=metadata))
        return docs
    
    def create_chunks(self, docs: list[Document]) -> tuple[list[Document], list[Document]]:
        """Create parent and child chunks for retrieval."""
        from app.runtime_settings import get_runtime_settings

        settings = get_runtime_settings().chunking
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            separators=["\n\n", "\n", ".", "?", "!", ";", " "],
        )
        parents = []
        children = []
        
        no_split_types = (
            {"table", "figure", "section_header", "caption"}
            if settings.preserve_structured_nodes else set()
        )
        
        for doc in docs:
            chunk_parent_id = str(uuid.uuid4())
            doc.metadata["chunk_id"] = chunk_parent_id
            parents.append(doc)
            
            node_type = doc.metadata.get("node_type", "")
            should_split = node_type not in no_split_types and len(doc.page_content) > settings.chunk_size
            
            if should_split:
                splits = splitter.split_documents([doc])
                for i, split in enumerate(splits):
                    split.metadata["chunk_parent_id"] = chunk_parent_id
                    split.metadata["chunk_id"] = f"{chunk_parent_id}_child_{i}"
                    children.append(split)
            else:
                child = Document(
                    page_content=doc.page_content,
                    metadata={**doc.metadata, "chunk_parent_id": chunk_parent_id, "chunk_id": f"{chunk_parent_id}_child_0"}
                )
                children.append(child)
        
        return parents, children
    
    def store_in_milvus(self, parents: list[Document], children: list[Document]) -> bool:
        """Store documents in Milvus with hybrid index (dense + BM25)."""
        if not parents or not children:
            return False
        
        try:
            child_store = MilvusStoreFactory.create_store(
                self.embeddings, self.milvus_uri, self.collection_name, is_child=True
            )
            child_store.add_documents(children)
            
            parent_store = MilvusStoreFactory.create_store(
                self.embeddings, self.milvus_uri, self.collection_name, is_child=False
            )
            parent_store.add_documents(parents)
            return True
        except Exception as e:
            print(f"Error storing in Milvus: {e}")
            return False

    async def store_in_milvus_async(self, parents: list[Document], children: list[Document]) -> bool:
        """Async version of store_in_milvus using aadd_documents."""
        if not parents or not children:
            return False

        try:
            child_store = MilvusStoreFactory.create_store(
                self.embeddings, self.milvus_uri, self.collection_name, is_child=True
            )
            await child_store.aadd_documents(children)

            parent_store = MilvusStoreFactory.create_store(
                self.embeddings, self.milvus_uri, self.collection_name, is_child=False
            )
            await parent_store.aadd_documents(parents)
            return True
        except Exception as e:
            print(f"Error storing in Milvus (async): {e}")
            return False


