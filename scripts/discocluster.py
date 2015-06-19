#!/usr/bin/env python

import os
import pysam
import argparse
import logging
logger = logging.getLogger(__name__)

from collections import defaultdict as dd
from bx.intervals.intersection import Intersecter, Interval


''' identify clusters of discordant read ends where one end is in BED file '''


class Coord:
    def __init__(self, chrom, start, end, strand, mchrom, mstart, mend, mstrand, label, bam_name):
        self.chrom   = chrom
        self.start   = int(start)
        self.end     = int(end)
        self.strand  = strand
        self.mchrom  = mchrom
        self.mstart  = int(mstart)
        self.mend    = int(mend)
        self.mstrand = mstrand
        self.label   = label
        self.bam     = bam_name

    def __gt__(self, other):
        if self.chrom == other.chrom:
            return self.start > other.start
        else:
            return self.chrom > other.chrom

    def __str__(self):
        return '%s\t%s:\t%s:%d-%d(%s) <--> %s:%d-%d(%s)' % (self.bam, self.label, self.chrom, self.start, self.end, self.strand, self.mchrom, self.mstart, self.mend, self.mstrand)


def interval_forest(bed_file):
    ''' build dictionary of interval trees '''
    forest = dd(Intersecter)

    with open(bed_file, 'r') as bed:
        for line in bed:
            chrom, start, end, label = line.strip().split()[:4]
            forest[chrom].add_interval(Interval(int(start), int(end), value=label))

    return forest


def get_coords(forest, bams, min_mapq=0, min_dist=10000):
    coords = []

    for bam in bams:
        tick = 10000000
        try:
            tick = int((bam.mapped + bam.unmapped) * 0.01)
            if tick == 0: tick = 1
            logger.debug('outputting status every %d reads (1 pct)' % tick)

        except ValueError as e:
            logger.debug('no index found, outputting status every %d reads' % tick)

        for i, read in enumerate(bam.fetch()):
            if not read.is_unmapped and not read.mate_is_unmapped and not read.is_duplicate:

                rchrom = bam.getrname(read.reference_id)
                rstart = read.reference_start
                rend   = read.reference_end

                rstr = '+'
                if read.is_reverse: rstr = '-'

                mdist = abs(read.reference_start-read.next_reference_start)
                if read.reference_id != read.next_reference_id: mdist=3e9

                if read.mapq >= min_mapq and mdist >= min_dist:
                    mchrom = bam.getrname(read.next_reference_id)
                    mstart = read.next_reference_start
                    mend   = mstart + len(read.seq)

                    mstr = '+'
                    if read.mate_is_reverse: mstr = '-'

                    if mchrom in forest:
                        for rec in forest[mchrom].find(mstart, mend):
                            coords.append(Coord(rchrom, rstart, rend, rstr, mchrom, mstart, mend, mstr, rec.value, os.path.basename(bam.filename)))
                            break

            if i % tick == 0:
                if read.is_unmapped:
                    logger.debug('parsed %d reads, last position unmapped' % i)
                else:
                    logger.debug('parsed %d reads, last position: %s:%d' % (i, bam.getrname(read.tid), read.pos))

    return coords


def subcluster_by_label(cluster):
    subclusters = dd(list)
    for c in cluster:
        subclusters[c.label].append(c)

    return subclusters.values()


def cluster(forest, coords, min_size=4, max_spacing=1000, output_padding=1000):
    logger.debug('sorting coordinates')
    coords.sort()

    cluster = []

    for c in coords:
        if len(cluster) == 0:
            cluster = [c]
        else:
            if c.chrom == cluster[-1].chrom and c.start - cluster[-1].end <= max_spacing:
                cluster.append(c)
            else:
                for cluster in subcluster_by_label(cluster):
                    if len(cluster) >= min_size:
                        cluster_chrom = cluster[0].chrom
                        cluster_start = cluster[0].start - output_padding
                        if cluster_start < 0: cluster_start = 0

                        cluster_end = cluster[-1].end + output_padding

                        bamlist = ','.join(list(set([c.bam  for c in cluster])))
                        labels = list(set([c.label for c in cluster]))
                        assert len(labels) == 1

                        if cluster_chrom not in forest or len(list(forest[cluster_chrom].find(cluster_start, cluster_end))) == 0:
                            print '%s\t%d\t%d\t%s\t%s\t%d' % (cluster_chrom, cluster_start, cluster_end, bamlist, labels[0], len(cluster))

                cluster = [c]


def main(args):
    logger.setLevel(logging.DEBUG)
    assert args.bam.endswith('.bam'), "not a BAM file: %s" % args.bam
    bams = [pysam.AlignmentFile(bam, 'rb') for bam in args.bam.split(',')]

    logger.debug('building interval trees for %s' % args.bed)
    forest = interval_forest(args.bed)

    logger.debug('fetching coordinates from %s' % args.bam)
    coords = get_coords(forest, bams)
    logger.debug('found %d anchored reads' % len(coords))

    cluster(forest, coords)


if __name__ == '__main__':
    FORMAT = '%(asctime)s %(message)s'
    logging.basicConfig(format=FORMAT)

    parser = argparse.ArgumentParser(description='identify clusters of discordant read ends where one end is in BED file')
    parser.add_argument('--bam', required=True, help='can be comma-delimited for multiple BAMs')
    parser.add_argument('--bed', required=True)
    args = parser.parse_args()
    main(args)