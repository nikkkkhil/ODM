import glob
import os
from opendm import log
from opendm import location
from pyproj import CRS

class GCPFile:
    def __init__(self, gcp_path):
        self.gcp_path = gcp_path
        self.entries = []
        self.raw_srs = ""
        self.srs = None
        self.read()
    
    def read(self):
        if self.exists():
            with open(self.gcp_path, 'r') as f:
                contents = f.read().decode('utf-8-sig').encode('utf-8').strip()
    
            lines = map(str.strip, contents.split('\n'))
            if lines:
                self.raw_srs = lines[0] # SRS
                self.srs = location.parse_srs_header(self.raw_srs)

                for line in lines[1:]:
                    if line != "" and line[0] != "#":
                        parts = line.split()
                        if len(parts) >= 6:
                            self.entries.append(line)                          
                        else:
                            log.ODM_WARNING("Malformed GCP line: %s" % line)

    def iter_entries(self):
        for entry in self.entries:
            yield self.parse_entry(entry)
    
    def parse_entry(self, entry):
        if entry:
            parts = entry.split()
            x, y, z, px, py, filename = parts[:6]
            extras = " ".join(parts[6:])
            return GCPEntry(float(x), float(y), float(z), float(px), float(py), filename, extras)

    def get_entry(self, n):
        if n < self.entries_count():
            return self.parse_entry(self.entries[n])

    def entries_count(self):
        return len(self.entries)
   
    def exists(self):
        return bool(self.gcp_path and os.path.exists(self.gcp_path))

    def wgs84_utm_zone(self):
        """
        Finds the UTM zone where the first point of the GCP falls into
        :return utm zone string valid for a coordinates header
        """
        if self.entries_count() > 0:
            entry = self.get_entry(0)
            longlat = CRS.from_epsg("4326")
            lon, lat = location.transform2(self.srs, longlat, entry.x, entry.y)
            utm_zone, hemisphere = location.get_utm_zone_and_hemisphere_from(lon, lat)
            return "WGS84 UTM %s%s" % (utm_zone, hemisphere)

    def create_utm_copy(self, gcp_file_output, filenames=None, rejected_entries=None):
        """
        Creates a new GCP file from an existing GCP file
        by optionally including only filenames and reprojecting each point to 
        a UTM CRS. Rejected entries can recorded by passing a list object to 
        rejected_entries.
        """
        if os.path.exists(gcp_file_output):
            os.remove(gcp_file_output)

        output = [self.wgs84_utm_zone()]
        target_srs = location.parse_srs_header(output[0])
        transformer = location.transformer(self.srs, target_srs)

        for entry in self.iter_entries():
            if filenames is None or entry.filename in filenames:
                entry.x, entry.y, entry.z = transformer.TransformPoint(entry.x, entry.y, entry.z)
                output.append(str(entry))
            elif isinstance(rejected_entries, list):
                rejected_entries.append(entry)

        with open(gcp_file_output, 'w') as f:
            f.write('\n'.join(output) + '\n')

        return gcp_file_output

    def make_filtered_copy(self, gcp_file_output, images_dir, min_images=3):
        """
        Creates a new GCP file from an existing GCP file includes
        only the points that reference images existing in the images_dir directory.
        If less than min_images images are referenced, no GCP copy is created.
        :return gcp_file_output if successful, None if no output file was created.
        """
        if not self.exists() or not os.path.exists(images_dir):
            return None
        
        if os.path.exists(gcp_file_output):
            os.remove(gcp_file_output)

        files = map(os.path.basename, glob.glob(os.path.join(images_dir, "*")))

        output = [self.raw_srs]
        files_found = 0
        
        for entry in self.iter_entries():
            if entry.filename in files:
                output.append(str(entry))
                files_found += 1

        if files_found >= min_images:
            with open(gcp_file_output, 'w') as f:
                f.write('\n'.join(output) + '\n')

            return gcp_file_output

class GCPEntry:
    def __init__(self, x, y, z, px, py, filename, extras=""):
        self.x = x
        self.y = y
        self.z = z
        self.px = px
        self.py = py
        self.filename = filename
        self.extras = extras
    
    def __str__(self):
        return "{} {} {} {} {} {} {}".format(self.x, self.y, self.z, 
                                             self.px, self.py, 
                                             self.filename, 
                                             self.extras).rstrip()