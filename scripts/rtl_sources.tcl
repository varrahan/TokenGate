proc collect_rtl {directory} {
    set sources [glob -nocomplain -types f -directory $directory *.v]
    foreach child [glob -nocomplain -types d -directory $directory *] {
        lappend sources {*}[collect_rtl $child]
    }
    return [lsort $sources]
}
