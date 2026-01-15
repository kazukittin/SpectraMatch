from pathlib import Path
from PIL import Image
import os
import gc
import logging

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
    def get_target_files(folder_path: Path) -> list[Path]:
        """指定フォルダ内の変換対象ファイルリストを取得"""
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
    def rename_folder_sequential(folder_path: Path, prefix: str = "", digits: int = 3):
        """
        フォルダ内の全画像を連番でリネームする（2パス方式で安全に）
        
        Args:
            folder_path: 対象フォルダ
            prefix: プレフィックス
            digits: 桁数
            
        Returns:
            tuple: (成功数, 失敗数, エラーリスト)
        """
        images = ImageConverter.get_all_images(folder_path)
        if not images:
            return 0, 0, []
        
        success_count = 0
        fail_count = 0
        errors = []
        
        # パス1: 全ファイルを一時的な名前にリネーム（衝突回避）
        temp_files = []
        for i, img in enumerate(images):
            temp_name = f"__temp_rename_{i:06d}__" + img.suffix
            temp_path = img.parent / temp_name
            try:
                os.rename(img, temp_path)
                temp_files.append(temp_path)
            except Exception as e:
                errors.append(f"{img.name}: {e}")
                fail_count += 1
            
            # 5000件ごとにメモリ解放
            if (i + 1) % 5000 == 0:
                gc.collect()
        
        # パス2: 一時ファイルを連番にリネーム
        for i, temp_path in enumerate(temp_files):
            ext = temp_path.suffix
            new_name = f"{prefix}{str(i + 1).zfill(digits)}{ext}"
            new_path = temp_path.parent / new_name
            try:
                os.rename(temp_path, new_path)
                logger.info(f"Renamed: {images[i].name} -> {new_name}")
                success_count += 1
            except Exception as e:
                errors.append(f"{temp_path.name}: {e}")
                fail_count += 1
            
            # 5000件ごとにメモリ解放
            if (i + 1) % 5000 == 0:
                gc.collect()
        
        # 最終メモリ解放
        gc.collect()
        
        return success_count, fail_count, errors
