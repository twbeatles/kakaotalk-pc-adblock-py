use clap::Parser;
use kakao_app::{run_with_args, Args};

fn main() {
    std::process::exit(run_with_args(Args::parse()));
}
