from pathlib import Path
from PIL import Image
import os
import gc
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class ImageConverter:
    """
    画像のフォーマット変換と元ファイルの削除を行うクラス
    """
    
    SUPPORTED_EXTENSIONS = {
        '.png', '.bmp', '.gif', '.webp', '.jpeg', '.tif', '.tiff'
    }
    
    # 連番リネーム対象の拡張子（JPGも含む）
    IMAGE_EXTENSIONS = {
        '.png', '.bmp', '.gif', '.webp', '.jpeg', '.jpg', '.tif', '.tiff'
    }
    
    @staticmethod
    def has_cache(file_path: Path, db=None) -> bool:
        """
        指定ファイルがキャッシュ（解析済み）かどうかをチェック
        
        Args:
            file_path: チェック対象のファイルパス
            db: ImageDatabaseインスタンス（オプション）
            
        Returns:
            bool: キャッシュがあればTrue
        """
        from .database import ImageDatabase
        
        should_close = False
        if db is None:
            db = ImageDatabase()
            should_close = True
            
        try:
            # ファイルが変更されていなければキャッシュあり
            return not db.is_file_changed(file_path)
        finally:
            if should_close:
                db.close()
    
    @staticmethod
    def get_target_files(folder_path: Path, check_cache: bool = False, db=None) -> list[Path]:
        """
        指定フォルダ内の変換対象ファイルリストを取得
        
        Args:
            folder_path: 対象フォルダ
            check_cache: Trueの場合、キャッシュがある画像をスキップ
            db: ImageDatabaseインスタンス（オプション）
        """
        if not folder_path.exists():
            return []
            
        targets = []
        for item in folder_path.iterdir():
            # 隠しファイル、一時ファイルは除外
            if item.name.startswith('.') or item.name.startswith('__temp_rename'):
                continue
                
            # 実在チェックかつファイルであること
            if not item.exists() or not item.is_file():
                continue
                
            if item.suffix.lower() in ImageConverter.SUPPORTED_EXTENSIONS:
                # ファイルサイズが0より大きいことも確認
                if item.stat().st_size > 0:
                    # キャッシュチェックが有効な場合、キャッシュがある画像はスキップ
                    if check_cache and ImageConverter.has_cache(item, db):
                        logger.info(f"Skipping cached file: {item.name}")
                        continue
                    targets.append(item)
        return targets
    
    @staticmethod
    def get_all_images(folder_path: Path) -> list[Path]:
        """指定フォルダ内の全画像ファイルリストを取得（リネーム用）"""
        if not folder_path.exists():
            return []
            
        targets = []
        for item in folder_path.iterdir():
            # 隠しファイル、一時ファイルは除外
            if item.name.startswith('.') or item.name.startswith('__temp_rename'):
                continue
                
            # 実在チェックかつファイルであること
            if not item.exists() or not item.is_file():
                continue
                
            if item.suffix.lower() in ImageConverter.IMAGE_EXTENSIONS:
                if item.stat().st_size > 0:
                    targets.append(item)
        # ファイル名でソート
        targets.sort(key=lambda x: x.name.lower())
        return targets

    @staticmethod
    def convert_to_jpg(file_path: Path):
        """
        画像をJPGに変換し、成功したら元ファイルを削除する
        
        Args:
            file_path: 変換元のファイルパス
            
        Returns:
            bool: 成功したかどうか
            str: エラーメッセージ（ある場合）
        """
        import time
        
        try:
            # JPEGのパスを生成
            jpg_path = file_path.with_suffix('.jpg')
            
            # .jpeg の場合はリネームで高速処理（画質劣化なし）
            if file_path.suffix.lower() == '.jpeg':
                try:
                    os.replace(file_path, jpg_path)
                    logger.info(f"Renamed .jpeg -> .jpg: {file_path}")
                    return True, None
                except Exception as e:
                    logger.warning(f"Failed to rename jpeg directly: {e}")
            
            # 既に同名のJPGが存在する場合は上書きすることになるが、
            # ImageMagickの挙動に合わせて変換を行う
            # ただし、PILで開いて保存する
            
            img = Image.open(file_path)
            # カラーモード変換 (RGBA -> RGBなど)
            rgb_im = img.convert('RGB')
            rgb_im.save(jpg_path, 'JPEG', quality=95)
            
            # 明示的にクローズ
            rgb_im.close()
            img.close()
            del rgb_im
            del img
            
            # ガベージコレクションを強制実行してファイルハンドルを解放
            gc.collect()
            
            # 変換が成功し、且つファイルが存在することを確認
            if jpg_path.exists() and jpg_path.stat().st_size > 0:
                # 元ファイルを削除（リトライあり）
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        time.sleep(0.05)  # 少し待機
                        os.remove(file_path)
                        logger.info(f"Converted and deleted: {file_path} -> {jpg_path}")
                        return True, None
                    except PermissionError:
                        if attempt < max_retries - 1:
                            time.sleep(0.2)  # リトライ前に少し待機
                            gc.collect()
                        else:
                            # 最終リトライでも失敗した場合、変換は成功しているので警告のみ
                            logger.warning(f"Converted but could not delete original: {file_path}")
                            return True, "変換成功（元ファイル削除失敗）"
            else:
                return False, "Conversion failed: output file invalid"
                
        except Exception as e:
            logger.error(f"Error converting {file_path}: {e}")
            return False, str(e)
    
    @staticmethod
    def rename_to_sequential(file_path: Path, index: int, prefix: str = "", digits: int = 3):
        """
        ファイルを連番でリネームする
        
        Args:
            file_path: リネーム対象のファイルパス
            index: 連番のインデックス（1から開始）
            prefix: ファイル名のプレフィックス（オプション）
            digits: 連番の桁数（デフォルト3桁 → 001, 002, ...）
            
        Returns:
            tuple: (成功したか, 新しいパスまたはエラーメッセージ)
        """
        try:
            # 新しいファイル名を生成
            ext = file_path.suffix
            new_name = f"{prefix}{str(index).zfill(digits)}{ext}"
            new_path = file_path.parent / new_name
            
            # 既に同名ファイルが存在する場合はスキップ
            if new_path.exists() and new_path != file_path:
                # 一時的な名前にリネームしてから
                temp_path = file_path.parent / f"_temp_{index}_{file_path.name}"
                os.rename(file_path, temp_path)
                return True, temp_path  # 後で再度リネーム
            
            if file_path != new_path:
                os.rename(file_path, new_path)
                logger.info(f"Renamed: {file_path.name} -> {new_name}")
            
            return True, new_path
            
        except Exception as e:
            logger.error(f"Error renaming {file_path}: {e}")
            return False, str(e)
    
    @staticmethod
    def _is_sequential_name(filename: str, digits: int = 3) -> bool:
        """
        ファイル名が連番形式（例: 001.jpg, 002.png）に一致するかチェック
        
        Args:
            filename: チェックするファイル名
            digits: 桁数（デフォルト3桁）
            
        Returns:
            bool: 連番形式に一致するならTrue
        """
        import re
        # ファイル名から拡張子を除いた部分を取得
        name_without_ext = Path(filename).stem
        # 指定桁数の数字のみかチェック（001〜999など）
        pattern = rf'^[0-9]{{{digits}}}$'
        return bool(re.match(pattern, name_without_ext))

    @staticmethod
    def is_already_processed(file_path: Path, digits: int = 3) -> bool:
        """
        ファイルが既に処理済み（JPG形式 かつ 連番ファイル名）かどうかを判定
        
        Args:
            file_path: 対象ファイルパス
            digits: 連番の桁数
            
        Returns:
            bool: 処理済みならTrue
        """
        # JPG以外は未処理とみなす
        if file_path.suffix.lower() != '.jpg':
            return False
            
        # ファイル名が連番形式かチェック
        return ImageConverter._is_sequential_name(file_path.name, digits)
    
    @staticmethod
    def rename_folder_sequential(folder_path: Path, prefix: str = "", digits: int = 3):
        """
        フォルダ内の全画像を連番でリネームする（2パス方式で安全に）
        既に連番形式のファイルはスキップし、使用済み番号を避けて割り当てる
        
        Args:
            folder_path: 対象フォルダ
            prefix: プレフィックス
            digits: 桁数
            
        Returns:
            tuple: (成功数, 失敗数, エラーリスト)
        """
        import re
        
        images = ImageConverter.get_all_images(folder_path)
        if not images:
            return 0, 0, []
        
        success_count = 0
        fail_count = 0
        errors = []
        skipped_count = 0
        
        # 既に使用されている連番を収集（拡張子関係なく番号だけ）
        used_numbers = set()
        files_to_rename = []
        
        for img in images:
            if ImageConverter._is_sequential_name(img.name, digits):
                # 連番形式のファイルから番号を抽出
                stem = img.stem  # 拡張子なしのファイル名
                try:
                    num = int(stem)
                    used_numbers.add(num)
                except ValueError:
                    pass
                skipped_count += 1
                logger.info(f"Skipped (already sequential): {img.name}")
            else:
                files_to_rename.append(img)
        
        if not files_to_rename:
            # リネーム対象がない場合
            return skipped_count, 0, []
        
        # パス1: 一時ファイル名にリネーム（衝突回避）
        renaming_entries = []
        
        for i, img in enumerate(files_to_rename):
            temp_name = f"__temp_rename_{i:06d}__" + img.suffix
            temp_path = img.parent / temp_name
            try:
                os.rename(img, temp_path)
                renaming_entries.append((temp_path, img.name))
            except Exception as e:
                errors.append(f"{img.name}: {e}")
                fail_count += 1
        
        # パス2: 一時ファイルを連番にリネーム（空き番号を使用）
        next_number = 1
        
        for j, (temp_path, original_name) in enumerate(renaming_entries):
            # 空き番号を探す
            while next_number in used_numbers:
                next_number += 1
            
            ext = temp_path.suffix
            new_name = f"{prefix}{str(next_number).zfill(digits)}{ext}"
            new_path = temp_path.parent / new_name
            
            try:
                os.rename(temp_path, new_path)
                logger.info(f"Renamed: {original_name} -> {new_name}")
                used_numbers.add(next_number)  # 使用済みに追加
                next_number += 1
                success_count += 1
            except Exception as e:
                errors.append(f"{temp_path.name}: {e}")
                fail_count += 1
            
            # 5000件ごとにメモリ解放
            if (j + 1) % 5000 == 0:
                gc.collect()
        
        # 最終メモリ解放
        gc.collect()
        
        # スキップ数を成功数に含める
        success_count += skipped_count
        
        return success_count, fail_count, errors
