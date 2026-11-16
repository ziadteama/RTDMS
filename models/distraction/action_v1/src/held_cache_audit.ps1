# Read-only SynDD fallback when the requested Python interpreter cannot start.
# All outputs remain in the ignored worktree directory. No media decoding or inference.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$outDir = Join-Path $PSScriptRoot '../_held_data'
New-Item -ItemType Directory -Force $outDir | Out-Null
Add-Type -ReferencedAssemblies System.IO.Compression,System.IO.Compression.FileSystem -TypeDefinition @'
using System;
using System.IO;
using System.IO.Compression;
using System.Collections.Generic;
public static class HeldCache {
  static byte[] Read(ZipArchive z, string name, string dtype) {
    using (var r = new BinaryReader(z.GetEntry(name+".npy").Open())) {
      var magic = r.ReadBytes(8);
      if (magic[6] != 1) throw new Exception("Only NPY v1 supported");
      string header = System.Text.Encoding.ASCII.GetString(r.ReadBytes(r.ReadUInt16()));
      if (!header.Contains("'descr': '"+dtype+"'") || !header.Contains("'fortran_order': False"))
        throw new Exception("Unexpected NPY layout: "+header);
      using (var m = new MemoryStream()) {r.BaseStream.CopyTo(m); return m.ToArray();}
    }
  }
  public static string[] Measure(string path, double[] starts, double[] ends, string[] labels,
                                 string driver, string split) {
    var output = new List<string>();
    using (var z = ZipFile.OpenRead(path)) {
      byte[] tb=Read(z,"t","<f8"), ob=Read(z,"ok","|b1"), lb=Read(z,"lm","<f4"), kb=Read(z,"kp","<f4");
      int n=tb.Length/8;
      if(ob.Length!=n || lb.Length!=n*478*2*4 || kb.Length!=n*17*3*4) throw new Exception("Shape mismatch");
      for(int seg=0;seg<starts.Length;seg++) {
        int count=0,face=0,wrist=0,pair=0,a=0,b=0,c=0;
        for(int i=0;i<n;i++) {
          double t=BitConverter.ToDouble(tb,i*8);
          if(t<starts[seg] || t>ends[seg]) continue;
          count++;
          bool usable=false;
          for(int j=9;j<=10;j++) if(BitConverter.ToSingle(kb,(i*51+j*3+2)*4)>=.3f) usable=true;
          if(usable) wrist++;
          if(ob[i]==0) continue;
          int l=i*956;
          double x10=BitConverter.ToSingle(lb,(l+20)*4),y10=BitConverter.ToSingle(lb,(l+21)*4);
          double x152=BitConverter.ToSingle(lb,(l+304)*4),y152=BitConverter.ToSingle(lb,(l+305)*4);
          double fh=Math.Sqrt(Math.Pow(x10-x152,2)+Math.Pow(y10-y152,2));
          if(double.IsNaN(fh) || fh<=1) continue;
          face++;
          double mx=(BitConverter.ToSingle(lb,(l+26)*4)+BitConverter.ToSingle(lb,(l+28)*4))/2.0;
          double my=(BitConverter.ToSingle(lb,(l+27)*4)+BitConverter.ToSingle(lb,(l+29)*4))/2.0;
          double d=double.PositiveInfinity;
          for(int j=9;j<=10;j++) {
            int k=(i*51+j*3)*4;
            float confidence=BitConverter.ToSingle(kb,k+8);
            if(float.IsNaN(confidence) || confidence<.3f) continue;
            double x=BitConverter.ToSingle(kb,k),y=BitConverter.ToSingle(kb,k+4);
            if(double.IsNaN(x) || double.IsNaN(y)) continue;
            d=Math.Min(d,Math.Sqrt(Math.Pow(x-mx,2)+Math.Pow(y-my,2))/fh);
          }
          if(!double.IsInfinity(d) && !double.IsNaN(d)) pair++;
          if(d<=.75) a++; if(d<=1) b++; if(d<=1.5) c++;
        }
        output.Add(string.Join(",",new object[]{Path.GetFileNameWithoutExtension(path),driver,split,labels[seg],starts[seg],ends[seg],count,face,wrist,pair,a,b,c}));
      }
    }
    return output.ToArray();
  }
}
'@
$split = Get-Content (Join-Path $PSScriptRoot '../../configs/syndd_split.json') -Raw | ConvertFrom-Json
$lines = [Collections.Generic.List[string]]::new()
$lines.Add('video,driver,split,label,start,end,frames,face_frames,wrist_frames,pair_frames,near_075,near_100,near_150')
$missing = [Collections.Generic.List[string]]::new()
$root = 'D:/rtdms-data/public/syndd/A1'
foreach ($annotation in (Get-ChildItem $root -Recurse -Filter *.csv)) {
    $driver = 'syndd_' + [regex]::Match($annotation.BaseName,'\d{4,6}').Value
    $rows = @(Import-Csv $annotation.FullName)
    $hasRear = @($rows | Where-Object { $_.'Camera View' -match '^Rear' -or $_.Filename -match '^Rear' }).Count -gt 0
    $lastFile = ''; $lastView = ''
    $segments = @()
    foreach ($r in $rows) {
        if ($r.Filename) { $lastFile = $r.Filename }
        if ($r.'Camera View') { $lastView = $r.'Camera View' }
        if ($hasRear -and $lastView -notmatch '^Rear') { continue }
        if (-not $r.'Start Time') { continue }
        $label = [regex]::Match($r.'Label (Primary)', '\d+').Value
        if ($label -notin @('0','1','4','11','12','13','14','15')) { continue }
        $block = [regex]::Match($lastFile,'\d+$').Value
        $segments += [pscustomobject]@{ block=$block; label=$label; start=([TimeSpan]::Parse($r.'Start Time')).TotalSeconds+.5; end=([TimeSpan]::Parse($r.'End Time')).TotalSeconds-.5 }
    }
    foreach ($group in ($segments | Group-Object block)) {
        $id = $driver.Replace('syndd_','')
        $cache = @(Get-ChildItem 'D:/rtdms-data/eval_cache/rich/fps10' -Filter "*${id}*_$($group.Name).npz")
        if ($cache.Count -ne 1) { $missing.Add("$driver block $($group.Name): $($cache.Count) caches"); continue }
        $g = @($group.Group)
        $result = [HeldCache]::Measure($cache[0].FullName,[double[]]$g.start,[double[]]$g.end,[string[]]$g.label,$driver,[string]$split.$driver)
        $lines.AddRange([string[]]$result)
    }
    Write-Output "$driver : $($lines.Count-1) segments"
}
$lines | Set-Content (Join-Path $outDir 'syndd_cache_segments.csv') -Encoding utf8
$missing | Set-Content (Join-Path $outDir 'syndd_cache_missing.txt') -Encoding utf8
$data = Import-Csv (Join-Path $outDir 'syndd_cache_segments.csv')
$summary = foreach ($group in ($data | Group-Object split,label)) {
    $r = $group.Group[0]
    $item = [ordered]@{dataset='syndd'; split=$r.split; label=$r.label; clips=$group.Count}
    foreach ($key in @('frames','face_frames','wrist_frames','pair_frames','near_075','near_100','near_150')) {
        $item[$key] = [long](($group.Group | Measure-Object $key -Sum).Sum)
    }
    [pscustomobject]$item
}
$summary | Export-Csv (Join-Path $outDir 'syndd_cache_summary.csv') -NoTypeInformation -Encoding utf8
$summary | Format-Table -AutoSize
Write-Output "Missing cache groups: $($missing.Count)"
