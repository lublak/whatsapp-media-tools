import argparse
import logging
from math import modf
import os
import re
from datetime import datetime

import piexif

img_filename_regex = re.compile(r'IMG-\d{8}-WA\d{4}\..+')
vid_filename_regex = re.compile(r'VID-\d{8}-WA\d{4}\..+')


def get_datetime(filename):
    date_str = filename.split('-')[1]
    return datetime.strptime(date_str, '%Y%m%d')

def exif_datestr_to_datetime(exifdate):
    return datetime.strptime(exifdate, "%Y:%m:%d %H:%M:%S")

def get_exif_datestr(filename):
    return get_datetime(filename).strftime("%Y:%m:%d %H:%M:%S")

def get_part_exif_datestr(filename):
    return get_datetime(filename).strftime("%Y:%m:%d")

def get_filepaths(path, recursive):
    all_filepaths = []
    if not recursive:
        abspath = os.path.abspath(path)
        all_filepaths += [(abspath, f) for f in os.listdir(abspath)
                          if os.path.isfile(os.path.join(abspath, f))]
    else:
        for dirpath, dirnames, filenames in os.walk(path):
            abspath = os.path.abspath(dirpath)
            all_filepaths += [(abspath, f) for f in filenames]
    return all_filepaths


def filter_filepaths(filepaths, allowed_ext):
    return [(fp, fn) for fp, fn in filepaths if os.path.splitext(fn)[-1] in allowed_ext]


def make_new_exif(filename):
    exif_dict = {
        'Exif': {piexif.ExifIFD.DateTimeOriginal: get_exif_datestr(filename)}}
    return piexif.dump(exif_dict)


def is_whatsapp_img(filename):
    return bool(img_filename_regex.match(filename))


def is_whatsapp_vid(filename):
    return bool(vid_filename_regex.match(filename))

def modFile(mod, filepath, filename, exifdate = None):
    if mod:
        if exifdate:
            date = exif_datestr_to_datetime(exifdate)
        else:
            date = get_datetime(filename)
        modTime = date.timestamp()
        os.utime(filepath, (modTime, modTime))

def main(path, recursive, mod, fix):
    logger.info('Validating arguments')
    if not os.path.exists(path):
        raise FileNotFoundError('Path specified does not exist')

    if not os.path.isdir(path):
        raise TypeError('Path specified is not a directory')

    logger.info('Listing files in target directory')
    filepaths = get_filepaths(path, recursive)
    logger.info(f'Total files: {len(filepaths)}')

    allowed_extensions = set(['.mp4', '.jpg', '.3gp', '.jpeg'])
    logger.info(f'Filtering for valid file extensions: {allowed_extensions}')
    filepaths = filter_filepaths(filepaths, allowed_ext=allowed_extensions)
    num_files = len(filepaths)
    logger.info(f'Valid files: {num_files}')

    logger.info('Begin processing files')
    abspath = os.path.abspath(path)
    progress_digits = len(str(num_files))
    abspath_len = len(abspath) + 1
    for i, (path, filename) in enumerate(filepaths):
        filepath = os.path.join(path, filename)
        logger.info(
            f'{i + 1:>{progress_digits}}/{num_files} - {filepath[abspath_len:]}')
        if filename.endswith('.mp4') or filename.endswith('.3gp'):
            if not is_whatsapp_vid(filename):
                logger.warning('File is not a valid WhatsApp video, skipping')
                continue
            date = get_datetime(filename)
            modTime = date.timestamp()
            os.utime(filepath, (modTime, modTime))

        elif filename.endswith('.jpg') or filename.endswith('.jpeg'):
            if not is_whatsapp_img(filename):
                logger.warning('File is not a valid WhatsApp image, skipping')
                continue

            try:
                exif_dict = piexif.load(filepath)
                exif_date = exif_dict['Exif'].get(piexif.ExifIFD.DateTimeOriginal)
                if exif_date:
                    if get_part_exif_datestr(filename) == exif_date.split(b" ")[0]:
                        logger.info('Exif date already exists, has the wrong date')
                        if not fix:
                            modFile(mod, filepath, filename)
                            continue
                    else:
                        logger.info('Exif date already exists, skipping')
                        modFile(mod, filepath, filename)
                        continue

                exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal] = get_exif_datestr(
                    filename)
                exif_bytes = piexif.dump(exif_dict)
            except piexif.InvalidImageDataError:
                logger.warning(f'Invalid image data, skipping')
                modFile(mod, filepath, filename)
                continue
            except ValueError:
                logger.warning(f'Invalid exif, overwriting with new exif')
                make_new_exif(filename)
            piexif.insert(exif_bytes, filepath)
            modFile(mod, filepath, filename)

    logger.info('Finished processing files')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=('Restore discarded Exif date information in WhatsApp media based on the filename. '
                     'For videos, only the created and modified dates are set.'))
    parser.add_argument('path', type=str, help='Path to WhatsApp media folder')
    parser.add_argument('-r', '--recursive', default=False,
                        action='store_true', help='Recursively process media')
    parser.add_argument('-m', '--mod', default=False,
                        action='store_true', help='Set file created/modified date on top of exif for images')
    parser.add_argument('-f', '--fix', default=False,
                        action='store_true', help='If the exif date is different from the filename it will be replaced')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s: %(message)s')
    logger = logging.getLogger('restore-exif')

    main(args.path, recursive=args.recursive, mod=args.mod, fix=args.fix)
