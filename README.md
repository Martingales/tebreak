## This fork is to try out some things to control memory leaking on HPCs.


## TEBreak 

[![Build Status](https://travis-ci.org/adamewing/tebreak.svg?branch=master)](https://travis-ci.org/adamewing/tebreak)

Contact: adam.ewing@mater.uq.edu.au

*Tools for analysing insertion mutations*

# Installation

## Python libraries:
This assumes a working installation of `pip`. Many of these prerequisites can be satisfied through installing [anaconda](https://conda.io/docs/user-guide/install/download.html).

```
pip install cython
pip install pysam
pip install scipy
pip install bx-python
```

If `pip install bx-python` fails you might need `liblzo2-dev` (via apt: `sudo apt-get install -y liblzo2-dev`).

## LAST (aligner)
```
wget http://last.cbrc.jp/last-716.zip
unzip last-716.zip
make CXXFLAGS=-O3 -C last-716 && sudo make install -C last-716
```

## HTSLIB / SAMtools / BCFtools
```
git clone https://github.com/samtools/htslib.git
git clone https://github.com/samtools/samtools.git
git clone https://github.com/samtools/bcftools.git

make -C htslib && sudo make install -C htslib
make -C samtools && sudo make install -C samtools
make -C bcftoools && sudo make install -C bcftools
```

## Minia (sequence assembler)
```
wget http://gatb-tools.gforge.inria.fr/versions/bin/minia-2.0.3-Linux.tar.gz
tar -xvf minia-2.0.3-Linux.tar.gz
sudo mv minia-2.0.3-Linux/bin/{dbgh5,dbginfo,h5dump,minia} /somewhere/in/your/$PATH
```

## Align (cython Smith-Waterman implementation)
```
git clone https://github.com/adamewing/align.git
cd align
python setup.py install
```

## Exonerate (aligner)
```
git clone https://github.com/adamewing/exonerate.git
cd exonerate
git checkout v2.4.0
autoreconf -i
./configure && make && make check && make install
```

# Test your installation
Assuming `$TB` is the tebreak directory created by `git clone` or unzipping/untarballing an archive:

```
$TB/tebreak/tebreak.py -b $TB/test/data/example.ins.bam -r $TB/test/data/Homo_sapiens_chr4_50000000-60000000_assembly19.fasta
$TB/tebreak/resolve.py -p example.ins.tebreak.pickle -i $TB/lib/teref.human.fa
```

This will generate some output to the terminal and the following files should exist in your working directory:

|filename                         | description |
|---------------------------------|-------------|
|`example.ins.tebreak.detail.out` | Details on all potential insertions detected by tebreak.py (probably not a useful final output, used for debugging) |
|`example.ins.tebreak.pickle`     | Data on detected insertions to be passed to resolve.py. Allows trying multiple parameters for resolve.py without needing to re-run completely. |
|`example.ins.tebreak.resolve.out`| Details on all potential insertions considered by resolve.py (probably not a useful final output, used for debugging) |
|`example.ins.tebreak.table.txt`  | Final output table. Often requires further filtering. |

The file `example.ins.tebreak.table.txt` should contain five insertions.

# Running TEBreak on real data

The parameters for the test run are the bare minimum required to run TEBreak and will be glacially slow on anything larger than the most trivial input. The following is the current recommendation for running TEBreak on WGS data with an average depth > 30x and should also suffice for capture-seq data.

## Generate BAM file(s)
Our recommendation is to use `bwa mem` with the following parameters. Let `$THREADS` be the number of CPU cores available on the system, `$RGID` be a read group id, `$SM` be a sample name, `$RAWBAM` be the output BAM filename, `$REF` be a bwa-indexed reference genome, `$FQ1` and `$FQ2` be .fastq files containing read 1 and read 2, respectively.


```
bwa mem -M -Y -t $THREADS -R "@RG\tID:$RGID\tSM:$BASE\tPL:ILLUMINA" $REF $FQ1 $FQ2 | samtools view -b - > $RAWBAM
```

## Mark Duplicate Reads
There's more than one way to do this, one option is to use [picard](https://broadinstitute.github.io/picard/). Let `$RAWBAM` be from the original alignment and `$BAM` be the BAM file used in subsequent steps.

```
java -jar picard.jar MarkDuplicates I=$RAWBAM O=$BAM M=metrics.out
```

## Build the relevant reference file(s)
This example assumes hg19/GRCh37 without the 'chr' prefix). The following builds a reference containing the locations of relevant human repeatmasker annotations for discordant read pair discovery:
```
cd $TB/lib
./make_discref_hg19.sh
```

Additionally, it may be helpful to build a mappability index using the `./human_mappability.sh` script, but it is not required for this example.

## Run tebreak.py
Note that the BAM file (`$BAM`) passed to -b can be a comma delimited list of BAM files or a `.txt` file containing a list of BAM files.

```
$TB/tebreak/tebreak.py -b $BAM -r $REF -p $THREADS -d $TB/lib/hg19.te.disctgt.txt -m $TB/lib/hg19.centromere_telomere.bed --max_ins_reads 1000 --debug
```

## Run resolve.py
This step annotates TE insertions based on a `.fasta` file containing insertion consensus sequences. This example is for human genomes, a refernce for mouse is also included.
Let $PICKLE be the `.pickle` file generated by `tebreak.py`.

```
/path/to/tebreak/tebreak/resolve.py -p $PICKLE -t $THREADS -i $TB/lib/teref.human.fa --min_split 4 --min_discord 4
```

## Filter the output
The results table output by `resolve.py` (`$TABLE`) will often contain false positives. To reduce these it is advisable to filter the output into a filtered table ('$FILTEREDTABLE`).

```
/path/to/tebreak/scripts/general_filter.py -t $TABLE -i $TB/lib/teref.human.fa -r $REF --numsplit 4 --numdiscord 4 > $FILTEREDTABLE
```

## Annotate the output
Finally, a script is included to annotate the TEBreak table. A useful included annotation source is the list of known non-reference insertions detected in human (hg19/GRCh37 coordinates).

```
$TB/scripts/annotate.py -t $FILTEREDTABLE -x $TB/lib/nonref.collection.hg19.bed.gz -n KnownNonRef --nonref > $FINALTABLE
```

## Getting help

Reporting [issues](https://github.com/adamewing/tebreak/issues) and questions through github is preferred versus e-mail.

For additional documentation, please find the manual in the [doc](https://github.com/adamewing/tebreak/tree/master/doc) subdirectory.
